# -*- coding: utf-8 -*-
"""结构化分析层（V3 第 1 步）：把「一句话 + 规则命中」拆成 V0.1 定的六个模块。

输出模块：
    1. 问题类型与客户诉求
    2. 已知事实（每条带来源与核实状态）
    3. 信息缺口（必须核实 / 可选补充）
    4. 争议点（客户说法与订单情况矛盾时）
    5. 处理建议与依据（依据只能来自规则库）
    6. 不确定性与风险

三条铁律（整个项目的底线，也是这个文件存在的原因）：
- 已知事实只能来自用户填的输入，或模型抽取；每条都要标来源和核实状态。
  不生成订单号、物流单号、凭证、金额这类输入里没有的东西。
- 依据只能来自规则库。规则没覆盖就不给结论，而不是编一条规则。
- 没发现争议就明说「暂未发现明显争议」，不许为了看起来完整而编一个争议。
"""
import re

from engine import FOLLOW_UP_QUESTION, RULES, analyze

# ---------------------------------------------------------------------------
# 一、客户诉求：从原话里抽「他到底想解决什么」
# 顺序有讲究：赔偿类优先（会覆盖退款类），因为转人工优先级最高
# ---------------------------------------------------------------------------
DEMAND_PATTERNS = [
    ("赔偿 / 追责", ["赔偿", "赔钱", "赔偿我", "退一赔三", "假货", "投诉", "起诉"]),
    ("退款", ["退款", "退钱", "能退", "我要退", "退掉", "不想要了"]),
    ("补发", ["补发", "重发", "再发一份", "再寄", "少了一件"]),
    ("换货", ["换货", "换一个", "换个新的", "重新发一个"]),
    ("开票", ["发票", "开票", "报销"]),
    ("催件 / 问时效", ["什么时候到", "多久能到", "催一下", "没动静", "还没到"]),
    ("要说法 / 要解释", ["给个说法", "怎么回事", "为什么", "解释一下"]),
]

# ---------------------------------------------------------------------------
# 二、争议点：客户说法 vs 订单情况（只对输入里真实出现的矛盾做判断）
# ---------------------------------------------------------------------------
CLIENT_SIGNALS = {
    "客户说没收到货": ["没收到", "没拿到", "找不到件", "根本没收到"],
    "客户说还没发货": ["没发货", "还没发", "一直没发", "未发货"],
    "客户说商品已使用": ["已经看了", "看完了", "已经用了", "用过了"],
    "客户说没收到交付物": ["没收到链接", "链接打不开", "没发给我"],
}

ORDER_SIGNALS = {
    "订单情况显示已签收": ["已签收", "签收"],
    "订单情况显示已发货": ["已发货", "已寄出", "运输中", "在路上"],
    "订单情况显示已交付": ["已交付", "已发送", "已发放"],
}

CONFLICT_RULES = [
    ("客户说没收到货", "订单情况显示已签收", "签收记录与客户说法不一致，需核对签收人与代收点"),
    ("客户说还没发货", "订单情况显示已发货", "客户认为未发货，但订单显示已发出，需核对物流单号"),
    ("客户说还没发货", "订单情况显示已签收", "客户认为未发货，但订单显示已签收，矛盾较大，需人工核实"),
    ("客户说商品已使用", "订单情况显示已交付", "已使用与已交付可能同时成立，需确认是否为同一商品与同一订单"),
]

# 缺信息时判断「必须 vs 可选」的关键词：涉及订单、时间、凭证的算必须
MUST_VERIFY_HINTS = ["单号", "时间", "状态", "凭证", "照片", "截图", "是否", "金额", "抬头"]

# 客户自己说已经提供过的证据：命中后，对应缺口就不再算「缺」
EVIDENCE_SIGNALS = {
    "照片/视频": ["照片", "拍照", "拍了", "截图", "视频", "录屏"],
    "快递单号": ["单号", "快递单", "运单号"],
}
# 缺口项里出现这些词，说明这条缺口要的是证据
EVIDENCE_GAP_HINTS = {
    "照片/视频": ["照片", "截图", "视频", "开箱"],
    "快递单号": ["单号"],
}


def _provided_evidence(facts):
    """从已知事实（不含「未提供」项）里找出客户已经给出的证据类型。"""
    provided = set()
    text = " ".join(f["content"] for f in facts if f["source"] != "缺失")
    for kind, words in EVIDENCE_SIGNALS.items():
        if any(word in text for word in words):
            provided.add(kind)
    return provided


def _drop_covered_gaps(gaps, provided):
    """客户已经给出的证据，不再列成缺口。"""
    keep, removed = [], []
    for item in gaps:
        covered = False
        for kind, words in EVIDENCE_GAP_HINTS.items():
            if kind in provided and any(word in item for word in words):
                covered = True
                break
        if covered:
            removed.append(item)
        else:
            keep.append(item)
    return keep, removed

# 去重时忽略这三种后缀：「订单信息 / 订单情况 / 订单状态」在这个语境下是一回事
_NORMALIZE_SUFFIXES = ("信息", "情况", "状态", "内容")


def _normalize(text):
    """把「订单信息 / 订单情况 / 订单状态」压成同一个词，便于比较重复。"""
    text = (text or "").strip()
    for suffix in _NORMALIZE_SUFFIXES:
        text = text.replace(suffix, "")
    return text.strip()


def _is_duplicate(text, candidates):
    """判断一段文字是否和已有内容重复（互相包含即算重复）。"""
    a = _normalize(text)
    if not a:
        return True
    for cand in candidates:
        b = _normalize(cand)
        if b and (a in b or b in a):
            return True
    return False


def _find_first(text, patterns):
    for label, words in patterns:
        for word in words:
            if word in text:
                return label, word
    return None, None


def customer_demand(question):
    """返回 (诉求标签, 命中的原话片段)。没有明显诉求时返回 ("未明确", "")。"""
    label, word = _find_first(question or "", DEMAND_PATTERNS)
    if label is None:
        return "未明确", ""
    return label, word


def _known_facts(question, product_type, order_info):
    """已知事实只来自输入，不补充任何输入里没有的东西。"""
    facts = []

    if (question or "").strip():
        facts.append({
            "content": "客户原话：" + question.strip(),
            "source": "客户陈述",
            "verified": False,
            "note": "客户单方陈述，未经核对",
        })

    if product_type and product_type not in ("未知", ""):
        facts.append({
            "content": "商品类型：" + product_type,
            "source": "商家 / 客服提供",
            "verified": False,
            "note": "由客服填写，未与订单核对",
        })

    if (order_info or "").strip():
        facts.append({
            "content": "订单及交付情况：" + order_info.strip(),
            "source": "商家 / 客服提供",
            "verified": False,
            "note": "由客服填写，未与后台核对（本工具不连接电商后台）",
        })

    missing = []
    if not (order_info or "").strip():
        missing.append("订单状态")
    if not product_type or product_type == "未知":
        missing.append("商品类型")
    for item in missing:
        facts.append({
            "content": "未提供：" + item,
            "source": "缺失",
            "verified": False,
            "note": "输入里没有，不能替客户假设",
        })

    return facts


def _information_gaps(rule, order_info):
    """把规则需要的确认项拆成「必须核实」和「可选补充」。"""
    if rule is None:
        return [], []

    must, optional = [], []
    has_order = bool((order_info or "").strip())
    for item in rule["need_info"]:
        needs_check = any(hint in item for hint in MUST_VERIFY_HINTS)
        if needs_check and not has_order:
            must.append(item)
        elif needs_check:
            must.append(item)
        else:
            optional.append(item)
    return must, optional


# 补充信息 → 缺口匹配表（人工维护的启发式；认不出的缺口不会自动抵消，宁可多问一句）
GAP_ALIASES = {
    "订单状态": ["订单", "已发货", "未发货", "已签收", "待发货", "已收货"],
    "下单时间": ["下单", "拍下", "买的时", "买的日"],
    "快递单号": ["单号", "运单"],
    "是否已签收": ["签收", "收到", "拿了"],
    "签收时间": ["签收", "收到", "几号", "哪天"],
    "商品是否影响二次销售": ["拆封", "没拆", "完好", "包装", "吊牌"],
    "收货地址是否准确": ["地址"],
    "最后更新时间": ["更新", "物流信息", "轨迹"],
    "是否已确认网点遗失": ["遗失", "丢件", "网点"],
    "商品照片或开箱视频": ["照片", "视频", "截图", "录屏"],
    "开箱照片": ["照片", "开箱"],
    "收到商品的照片": ["照片", "图"],
    "订单明细": ["明细", "规格", "型号", "下单的"],
    "是否已收到下载链接/账号": ["链接", "账号", "收到了"],
    "失败截图": ["截图"],
    "交付时间": ["交付", "发的时", "什么时候发"],
    "使用记录": ["看了", "用了", "使用", "学过"],
    "商品页面截图": ["截图", "页面"],
    "实际内容截图": ["截图", "内容"],
    "发票抬头与税号": ["抬头", "税号"],
    "开票金额": ["金额", "多少钱"],
    "原发票状态": ["发票"],
    "正确抬头信息": ["抬头"],
    "当前活动页面截图": ["截图", "活动"],
}


# 「XX时间」这类缺口，必须是补充信息里真的出现了时间，才算补齐。
# 否则「物流显示已签收」会把「签收时间」误判成已补齐（实测踩过）。
TIME_EVIDENCE_PATTERN = re.compile(
    r"\d{1,2}\s*[号日]"          # 1号 / 21日
    r"|\d{1,2}\s*月"             # 11月
    r"|\d{4}\s*[-/年]\s*\d{1,2}"  # 2026-11 / 2026年11
    r"|昨天|今天|前天|大前天|上周|本周|上个月|这个月"
    r"|星期[一二三四五六日天]"
    r"|\d{1,2}\s*点"             # 下午3点
)


def _time_mentioned(text):
    return bool(TIME_EVIDENCE_PATTERN.search(text or ""))


def _filled_by_supplement(gaps, supplement):
    """补充信息里已经回答了的缺口，就不该再列成「缺」。"""
    if not (supplement or "").strip():
        return list(gaps), []
    keep, filled = [], []
    for item in gaps:
        aliases = GAP_ALIASES.get(item, [])
        # 「XX时间」光有「签收」「收到」不够，必须真给出时间
        if "时间" in item and not _time_mentioned(supplement):
            keep.append(item)
            continue
        if aliases and any(word in supplement for word in aliases):
            filled.append(item)
        else:
            keep.append(item)
    return keep, filled


def _conflicts(question, order_info, supplement=""):
    """只在两边的说法都真实出现时才报冲突。补充信息算「订单侧」的证据。"""
    text_client = question or ""
    text_order = (order_info or "") + " " + (supplement or "")

    found_client = {label for label, words in CLIENT_SIGNALS.items()
                    if any(word in text_client for word in words)}
    found_order = {label for label, words in ORDER_SIGNALS.items()
                   if any(word in text_order for word in words)}

    conflicts = []
    for client_label, order_label, note in CONFLICT_RULES:
        if client_label in found_client and order_label in found_order:
            conflicts.append({
                "client_says": client_label,
                "order_says": order_label,
                "note": note,
                "handle": "两边都摆出来，由人工核实，不替任何一方下结论",
            })
    return conflicts


def _uncertainty(rule, result, must_gaps, conflicts, demand, covered_evidence=()):
    items = []

    if rule is None:
        items.append("规则库没有覆盖这类问题，本工具不给结论性答复。")

    if result.get("source") in ("模型", "同义词"):
        items.append("问题分类由「{0}」给出，可能有误，需客服确认。".format(result["source"]))
    if result.get("confidence") == "低":
        items.append("分类置信度低，请不要直接照搬答复。")

    if must_gaps:
        items.append("还缺 {0} 项关键信息，现在的结论只是初步判断。".format(len(must_gaps)))

    for conflict in conflicts:
        items.append("存在矛盾：" + conflict["note"] + "。")

    if covered_evidence:
        items.append(
            "客户已表示提供「{0}」，答复前先确认是否真的收到，不要再重复索要。".format(
                "、".join(covered_evidence))
        )

    if demand == "未明确":
        items.append("客户诉求不明确，建议先问清他要的是退款、补发还是解释。")

    if result.get("escalate"):
        items.append("本单涉及赔付 / 投诉 / 例外承诺，AI 不独立担责，必须人工处理。")

    if not result.get("basis"):
        items.append("没有可引用的规则依据，不要向客户承诺具体处理结果。")

    return items


def build_report(question, product_type="未知", order_info="", mode="auto", use_llm=True,
                 supplement="", _diff=True):
    """生成结构化分析报告。

    Args:
        question: 客户原话（必填）。
        product_type: 商品类型。
        order_info: 订单及交付情况。
        mode: 传给 engine.analyze 的识别模式。
        use_llm: 是否允许模型做「事实与缺口抽取」。
        supplement: 补充信息（单轮再分析）。给了之后会多输出一节「这次补充改变了什么」。
    Returns:
        dict：problem / known_facts / gaps / conflicts / advice / uncertainty /
              follow_up / changes / meta
    """
    result = analyze(question, product_type=product_type, order_info=order_info,
                     mode=mode, supplement=supplement)
    rule = None
    for item in RULES:
        if item["id"] == result["rule_id"]:
            rule = item
            break

    demand, demand_word = customer_demand(question)
    facts = _known_facts(question, product_type, order_info)
    if (supplement or "").strip():
        facts.append({
            "content": "补充信息：" + supplement.strip(),
            "source": "补充信息 · 待核实",
            "verified": False,
            "note": "后补的内容，仍需与订单后台核对",
        })
    must_gaps, optional_gaps = _information_gaps(rule, order_info)
    conflicts = _conflicts(question, order_info, supplement)

    # 模型抽取（可选）：只补「客户说了什么」，与已有内容重复的一律丢掉
    extraction = None
    if use_llm and mode in ("auto", "llm") and (question or "").strip():
        extraction = _try_extract(question, product_type, order_info, supplement)
        if extraction:
            spoken = " ".join(x for x in [question, order_info, product_type] if x)
            existing_facts = [f["content"] for f in facts]

            for item in extraction.get("facts", [])[:4]:
                content = str(item.get("content", "")).strip()
                if not content:
                    continue
                # 原话已经整段列在第一条事实里，模型再复述一遍没有信息量
                if content in spoken:
                    continue
                if _is_duplicate(content, existing_facts):
                    continue
                facts.append({
                    "content": content,
                    "source": "模型抽取 · 待核实",
                    "verified": False,
                    "note": "模型从对话中抽取，不是事实认定",
                })
                existing_facts.append(content)

            # 缺口去重：和「未提供：X」或规则已要求的项重复的，不再列第二遍
            missing_inputs = [f["content"].replace("未提供：", "")
                              for f in facts if f["source"] == "缺失"]
            gap_candidates = list(must_gaps) + list(optional_gaps) + missing_inputs
            for item in extraction.get("gaps", [])[:4]:
                item = str(item).strip()
                if not item or _is_duplicate(item, gap_candidates):
                    continue
                optional_gaps.append(item)
                gap_candidates.append(item)

            if extraction.get("demand") and demand == "未明确":
                demand = str(extraction["demand"]).strip()[:20]

    # 客户自己已经给出的证据，不再算「缺」——否则会出现「客户已拍照，却让客服再要照片」
    provided = _provided_evidence(facts)
    must_gaps, dropped_must = _drop_covered_gaps(must_gaps, provided)
    optional_gaps, dropped_optional = _drop_covered_gaps(optional_gaps, provided)
    covered = dropped_must + dropped_optional

    # 补充信息回答掉的缺口，也不再算「缺」
    filled = []
    if (supplement or "").strip():
        must_gaps, filled_must = _filled_by_supplement(must_gaps, supplement)
        optional_gaps, filled_opt = _filled_by_supplement(optional_gaps, supplement)
        filled = filled_must + filled_opt

    # 建议文案是规则库原文，不擅自改写；但客户已给证据时，必须提示客服跳过「索要凭证」这一步
    advice_note = ""
    if covered:
        advice_note = (
            "客户已提供「{0}」：本条建议里「索要凭证」那一步请跳过，先确认已收到，"
            "再直接进入核实与补发/退款流程。".format("、".join(covered))
        )
    if filled:
        extra = "本次补充信息已补齐「{0}」，可以直接进入核实与处理流程。".format("、".join(filled))
        advice_note = (advice_note + " " + extra).strip() if advice_note else extra

    uncertainty = _uncertainty(rule, result, must_gaps, conflicts, demand, covered)
    if filled:
        uncertainty.append(
            "本次补充信息补齐了 {0} 项缺口，结论已据此更新；原始对话仍然保留。".format(len(filled))
        )

    report = {
        "problem": {
            "type": result["category"],
            "rule_id": result["rule_id"],
            "demand": demand,
            "demand_quote": demand_word,
            "escalate": bool(result["escalate"]),
        },
        "known_facts": facts,
        "gaps": {
            "must": must_gaps,
            "optional": optional_gaps,
            "covered": covered,
            "filled": filled,
            "note": "「必须核实」不补齐就不能定责；「可选补充」缺了也能给初步建议。",
        },
        "conflicts": conflicts,
        "conflicts_note": "暂未发现明显争议。" if not conflicts else "发现 {0} 处矛盾，需人工核实。".format(len(conflicts)),
        "advice": {
            "text": result["advice"],
            "basis": result["basis"],
            "source": result["source"],
            "confidence": result["confidence"],
            "note": advice_note,
        },
        "uncertainty": uncertainty,
        "follow_up": list(result.get("follow_up") or []),
        "changes": [],
        "meta": {
            "mode": mode,
            "llm_status": result.get("llm_status", "skipped"),
            "llm_extraction": bool(extraction),
            "has_supplement": bool((supplement or "").strip()),
        },
    }

    # 单轮再分析：和「没有补充信息」时比，到底改变了什么
    if (supplement or "").strip() and _diff:
        baseline = build_report(question, product_type=product_type, order_info=order_info,
                                mode=mode, use_llm=use_llm, supplement="", _diff=False)
        report["changes"] = _diff_reports(baseline, report)
    return report


def _diff_reports(prev, cur):
    """对比「补充前 / 补充后」，指出是哪一类信息改变了结论。"""
    changes = []
    p, c = prev["problem"], cur["problem"]

    if p["rule_id"] != c["rule_id"] or p["type"] != c["type"]:
        if p["escalate"] and not c["escalate"]:
            changes.append("分类从「{0}」变成「{1}」（{2}），现在可以给建议了。".format(
                p["type"], c["type"], c["rule_id"]))
        elif c["escalate"] and not p["escalate"]:
            changes.append("分类从「{0}」变成「{1}」，需要转人工。".format(p["type"], c["type"]))
        else:
            changes.append("分类从「{0}」变成「{1}」（{2}）。".format(p["type"], c["type"], c["rule_id"]))

    filled = cur["gaps"].get("filled") or []
    if filled:
        changes.append("补齐了缺口：" + "、".join(filled) + "。")

    before_must = len(prev["gaps"]["must"])
    after_must = len(cur["gaps"]["must"])
    if after_must < before_must:
        changes.append("必须核实项从 {0} 项减少到 {1} 项。".format(before_must, after_must))
    elif after_must > before_must:
        changes.append("必须核实项从 {0} 项增加到 {1} 项（补充信息带来了新的待核实点）。".format(
            before_must, after_must))

    prev_notes = [item["note"] for item in prev["conflicts"]]
    new_conflicts = [item["note"] for item in cur["conflicts"] if item["note"] not in prev_notes]
    if new_conflicts:
        changes.append("新增矛盾：" + "；".join(new_conflicts) + "。")

    if not changes:
        changes.append("这次补充没有改变分类与缺口，只作为事实记录下来，原有结论不变。")
    return changes


def _try_extract(question, product_type, order_info, supplement=""):
    """模型抽取事实与缺口；不可用或失败时返回 None，绝不编造。"""
    try:
        import llm_classifier
    except Exception:
        return None
    if not llm_classifier.available():
        return None
    try:
        return llm_classifier.extract(question, product_type=product_type,
                                      order_info=order_info, supplement=supplement)
    except Exception:
        return None


def format_report(report):
    """命令行展示用：把结构化报告排成一段可读文本。"""
    lines = []
    problem = report["problem"]
    lines.append("【一、问题类型与客户诉求】")
    lines.append("  类型：" + str(problem["type"]) + "（规则 " + str(problem["rule_id"]) + "）")
    lines.append("  诉求：" + str(problem["demand"]) +
                 ("（原话：「" + problem["demand_quote"] + "」）" if problem["demand_quote"] else ""))

    lines.append("【二、已知事实】")
    for fact in report["known_facts"]:
        lines.append("  · " + fact["content"] + "　［" + fact["source"] + "］" + fact["note"])

    lines.append("【三、信息缺口】")
    if report["gaps"]["must"]:
        lines.append("  必须核实：" + "、".join(report["gaps"]["must"]))
    if report["gaps"]["optional"]:
        lines.append("  可选补充：" + "、".join(report["gaps"]["optional"]))
    if report["gaps"].get("covered"):
        lines.append("  客户已提供：" + "、".join(report["gaps"]["covered"]) + "（先确认收到，不要再索要）")
    if report["gaps"].get("filled"):
        lines.append("  本次补充已补齐：" + "、".join(report["gaps"]["filled"]))
    if not report["gaps"]["must"] and not report["gaps"]["optional"]:
        lines.append("  暂无需补充（规则未要求额外信息）")

    lines.append("【四、争议点】")
    if report["conflicts"]:
        for item in report["conflicts"]:
            lines.append("  · " + item["client_says"] + " / " + item["order_says"] + "：" + item["note"])
    else:
        lines.append("  " + report["conflicts_note"])

    lines.append("【五、处理建议与依据】")
    lines.append("  " + report["advice"]["text"])
    if report["advice"].get("note"):
        lines.append("  注意：" + report["advice"]["note"])
    if report["advice"]["basis"]:
        lines.append("  依据：" + report["advice"]["basis"])
    else:
        lines.append("  依据：无（规则库未覆盖，不引用任何规则）")

    lines.append("【六、不确定性与风险】")
    for item in report["uncertainty"]:
        lines.append("  · " + item)

    if report["follow_up"]:
        lines.append("【可先发给客户】" + report["follow_up"][0])

    if report.get("changes"):
        lines.append("【七、这次补充改变了什么】")
        for item in report["changes"]:
            lines.append("  · " + item)
    return "\n".join(lines)
