# -*- coding: utf-8 -*-
"""售后工单辅助台 · 规则引擎 V1

设计原则（也是产品的边界）：
1. 规则明确 + 信息齐全 → 给出答复建议与规则依据
2. 关键信息缺失       → 提示补充，不硬答
3. 赔付/投诉/例外承诺/规则未覆盖 → 转人工，AI 不独立担责

规则是模拟的，不代表任何真实商家的售后制度。
"""

# ---------------------------------------------------------------------------
# 转人工：优先级最高，命中即直接转人工，不被下面的规则覆盖
# ---------------------------------------------------------------------------
ESCALATE_KEYWORDS = [
    "赔", "补偿", "投诉", "起诉", "曝光", "12315", "假货", "举报",
    "退一赔三", "媒体", "律师", "报警",
]

# ---------------------------------------------------------------------------
# 规则库：5 个类别 × 3 条 = 15 条
# 每条包含：触发词、需要向客户确认的信息、答复建议、规则依据
# ---------------------------------------------------------------------------
RULES = [
    # ---------------- 一、退货退款 ----------------
    {
        "id": "R101",
        "group": "退货退款",
        "category": "退款 · 未发货取消",
        "keywords": ["还没发货", "未发货", "取消订单", "不想要了", "没发货"],
        "need_info": ["订单状态", "下单时间"],
        "advice": "确认订单尚未发货后，可协助客户取消并原路退款；已付款未发货的订单，按平台规则支持取消。",
        "basis": "R101-1 未发货订单支持取消；R101-2 退款原路返回，到账时间以支付渠道为准（1—7 个工作日）。",
        "escalate": False,
    },
    {
        "id": "R102",
        "group": "退货退款",
        "category": "退款 · 已发货拦截",
        "keywords": ["拦截", "拒收", "已经发货", "已发货", "不要了"],
        "need_info": ["快递单号", "是否已签收"],
        "advice": "包裹已发出但未签收时，可协助尝试拦截或引导客户拒收；签收后退回按退货流程处理。",
        "basis": "R102-1 未签收可尝试拦截；R102-2 拦截失败需引导拒收，运费责任按规则判定。",
        "escalate": False,
    },
    {
        "id": "R103",
        "group": "退货退款",
        "category": "退款 · 签收后七天无理由",
        "keywords": ["七天", "无理由", "退货", "想退", "退掉"],
        "need_info": ["签收时间", "商品是否影响二次销售"],
        "advice": "确认在签收后七天内且商品完好、不影响二次销售，可按无理由退货处理；定制、鲜活、已拆封虚拟商品除外。",
        "basis": "R103-1 七天无理由需签收后七日内；R103-2 影响二次销售不支持无理由退货。",
        "escalate": False,
    },

    # ---------------- 二、物流异常 ----------------
    {
        "id": "R201",
        "group": "物流异常",
        "category": "物流 · 显示签收但未收到",
        "keywords": ["签收", "没收到", "没看到", "代收点", "门卫"],
        "need_info": ["快递单号", "收货地址是否准确"],
        "advice": "先核对物流轨迹与签收人，引导客户确认代收点、快递柜或门卫；确认未收到则协助发起物流查件。",
        "basis": "R201-1 显示签收未收到，先自查代收点；R201-2 查件由商家协助发起，不由客服直接判定赔付。",
        "escalate": False,
    },
    {
        "id": "R202",
        "group": "物流异常",
        "category": "物流 · 轨迹长时间未更新",
        "keywords": ["没更新", "一直不动", "物流信息", "好几天", "卡住"],
        "need_info": ["快递单号", "最后更新时间"],
        "advice": "核对最后一跳物流时间；超出正常时效则协助发起催件，并向客户说明预计更新节点。",
        "basis": "R202-1 超时未更新可催件；R202-2 不承诺具体到达时间。",
        "escalate": False,
    },
    {
        "id": "R203",
        "group": "物流异常",
        "category": "物流 · 丢件",
        "keywords": ["丢件", "丢了", "不见了", "找不到件"],
        "need_info": ["快递单号", "是否已确认网点遗失"],
        "advice": "确认网点判定遗失后，为客户补发或按规则退款；赔付金额按快递公司理赔规则，客服不做额外承诺。",
        "basis": "R203-1 丢件由快递方理赔；R203-2 商家先行补发或退款，再与快递方结算。",
        "escalate": False,
    },

    # ---------------- 三、商品质量与发错 ----------------
    {
        "id": "R301",
        "group": "商品质量",
        "category": "商品 · 破损",
        "keywords": ["破损", "坏了", "碎了", "压坏", "裂了"],
        "need_info": ["商品照片或开箱视频", "订单明细"],
        "advice": "请客户提供照片/视频，核实为运输破损则走补发或退款流程；责任归属按平台规则判定。",
        "basis": "R301-1 破损类需凭证；R301-2 运输破损由商家先行处理，再向快递追责。",
        "escalate": False,
    },
    {
        "id": "R302",
        "group": "商品质量",
        "category": "商品 · 少发漏发",
        "keywords": ["少发", "漏发", "少了", "缺件", "少了一件"],
        "need_info": ["开箱照片", "订单明细"],
        "advice": "核对订单明细与开箱照片，确认少发后优先补发；客户不接受补发可改退款。",
        "basis": "R302-1 少发需订单与照片核对；R302-2 补发优先于退款。",
        "escalate": False,
    },
    {
        "id": "R303",
        "group": "商品质量",
        "category": "商品 · 发错货",
        "keywords": ["发错", "错发", "不是我买的", "颜色不对", "型号不对"],
        "need_info": ["收到商品的照片", "订单明细"],
        "advice": "核实为发错货，安排换货或退货退款，来回运费由商家承担。",
        "basis": "R303-1 发错货商家承担运费；R303-2 换货需客户先退回错发商品。",
        "escalate": False,
    },

    # ---------------- 四、虚拟商品 ----------------
    {
        "id": "R401",
        "group": "虚拟商品",
        "category": "虚拟商品 · 未交付或交付失败",
        "keywords": ["链接失效", "打不开", "没收到链接", "账号不对", "未交付", "网盘"],
        "need_info": ["是否已收到下载链接/账号", "失败截图"],
        "advice": "核实确实未成功交付（链接失效、账号错误），立即补发或按规则退款。",
        "basis": "R401-1 交付失败由商家负责补发或退款；R401-2 需保留失败截图作为凭证。",
        "escalate": False,
    },
    {
        "id": "R402",
        "group": "虚拟商品",
        "category": "虚拟商品 · 已交付已使用",
        "keywords": ["已经看了", "看过了", "看完了", "已经用了", "使用了", "下载了", "已经激活", "已交付"],
        "need_info": ["交付时间", "使用记录"],
        "advice": "虚拟商品交付并使用后，通常不支持无理由退款；若存在内容与描述不符，另行核实。",
        "basis": "R402-1 虚拟商品交付后不支持无理由退款；R402-2 需区分「已使用」与「未成功交付」。",
        "escalate": False,
    },
    {
        "id": "R403",
        "group": "虚拟商品",
        "category": "虚拟商品 · 内容与描述不符",
        "keywords": ["和描述不符", "货不对板", "内容不符", "不是这个课"],
        "need_info": ["商品页面截图", "实际内容截图"],
        "advice": "核对商品描述与实际内容；确属描述不符，按规则退款或补偿，并同步修改商品页。",
        "basis": "R403-1 描述不符商家担责；R403-2 需同时核对页面快照与实际交付内容。",
        "escalate": False,
    },

    # ---------------- 五、发票与其他 ----------------
    {
        "id": "R501",
        "group": "发票与凭证",
        "category": "发票 · 开具",
        "keywords": ["发票", "开票", "税号", "抬头"],
        "need_info": ["发票抬头与税号", "开票金额"],
        "advice": "收集抬头、税号与金额，登记开票需求并告知出票周期。",
        "basis": "R501-1 开票需抬头与税号；R501-2 出票周期以平台开票系统为准。",
        "escalate": False,
    },
    {
        "id": "R502",
        "group": "发票与凭证",
        "category": "发票 · 重开或修改",
        "keywords": ["改抬头", "重开", "换发票", "发票开错"],
        "need_info": ["原发票状态", "正确抬头信息"],
        "advice": "未开出可直接修改；已开出需按平台规则作废重开，跨月或已抵扣的需走红冲流程。",
        "basis": "R502-1 已开票修改受税务规则限制；R502-2 跨月红冲需人工审核。",
        "escalate": False,
    },
    {
        "id": "R503",
        "group": "发票与凭证",
        "category": "价保 · 差价与优惠",
        "keywords": ["价保", "降价", "优惠券", "差价", "便宜了"],
        "need_info": ["下单时间", "当前活动页面截图"],
        "advice": "核对是否在价保期内且为同一商品同一规格；符合条件的按规则退差价。",
        "basis": "R503-1 价保需在有效期内；R503-2 叠加优惠券的差价计算方式以活动规则为准。",
        "escalate": False,
    },
]


def _all_text(question, product_type, order_info):
    """把客户原话、商品类型、订单情况拼成待匹配文本。"""
    parts = [question or "", product_type or "", order_info or ""]
    return " ".join(part for part in parts if part).strip()


def _escalate_hit(text):
    """检查是否命中必须转人工的情形。"""
    for word in ESCALATE_KEYWORDS:
        if word in text:
            return word
    return None


def _analyze_v1(question, product_type="未知", order_info=""):
    """V1 规则版分析（关键词匹配）。V2 的 analyze 会在这层之上加模型与同义词。

    Args:
        question: 客户原话。
        product_type: 商品类型（下拉框选择）。
        order_info: 订单与交付情况描述。
    Returns:
        dict：category / advice / basis / need_info / escalate / reason / rule_id / confidence
    """
    text = _all_text(question, product_type, order_info)

    if (question or "").strip() == "":
        return {
            "rule_id": "-",
            "category": "输入为空",
            "advice": "请输入客户问题后再试。",
            "basis": "",
            "need_info": [],
            "escalate": False,
            "reason": "空输入",
            "confidence": "—",
        }

    hit_word = _escalate_hit(text)
    if hit_word is not None:
        return {
            "rule_id": "R000",
            "category": "转人工 · 争议与授权",
            "advice": "此问题涉及赔付、投诉或例外承诺，AI 不给出结论性答复，请转交人工主管处理。",
            "basis": "R000-1 涉及赔偿与例外承诺必须人工授权；R000-2 投诉升级类问题不得由 AI 直接回复。",
            "need_info": [],
            "escalate": True,
            "reason": "命中转人工关键词：" + hit_word,
            "confidence": "高",
        }

    scored = []
    for rule in RULES:
        hits = [kw for kw in rule["keywords"] if kw in text]
        if hits:
            longest = max(len(kw) for kw in hits)
            # 商品类型与规则类别一致时加权：虚拟商品的售后规则明显不同于实物
            boost = 2 if (product_type == "虚拟商品" and rule["group"] == "虚拟商品") else 0
            scored.append((len(hits) + boost, longest, rule, hits))

    if not scored:
        return {
            "rule_id": "-",
            "category": "转人工 · 规则未覆盖",
            "advice": "规则库中没有匹配的售后类型，请转交人工判断，不要由 AI 自行答复。",
            "basis": "R000-3 规则未覆盖的问题不生成答复建议。",
            "need_info": [],
            "escalate": True,
            "reason": "无规则命中",
            "confidence": "低",
        }

    # 命中条数多者优先；同分时命中词更长（更具体）者优先
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    count, longest, best, hits = scored[0]

    confidence = "高" if (count >= 2 or longest >= 4) else "中"
    return {
        "rule_id": best["id"],
        "category": best["category"],
        "advice": best["advice"],
        "basis": best["basis"],
        "need_info": list(best["need_info"]),
        "escalate": bool(best["escalate"]),
        "reason": "命中 " + best["id"] + "（" + "、".join(hits) + "）",
        "confidence": confidence,
    }


# ===========================================================================
# V2 分层识别（2026-11-21 加入）
#
#   第 1 层  关键词规则     _analyze_v1()，V1 行为完全不变，保证 12/12 不回退
#   第 2 层  模型意图分类   只在第 1 层没命中时调用；模型只给规则 ID，不写答复
#   第 3 层  同义词兜底     没有 key / 模型失败时才用；人工维护，天花板低
#   第 4 层  转人工        附带一句客服可直接发出的澄清话术
#
# 为什么模型放在关键词之后：关键词命中的问题本来就能答对，没必要花 token；
# 关键词答不出的（换说法）才是真问题，也正是模型擅长的地方。
# ===========================================================================

# 同义词兜底表：按「意图」整理的口语说法，不是照着测试句写的。
# 注意：这张表会包含一些测试用例里的说法，所以它命中 6/6 只能说明「按意图整理有效」，
#      不能证明泛化能力——泛化必须用真实客服用语验证。
SYNONYMS = {
    # 一、退货退款
    "R101": ["还没发", "一直没发", "不发货", "不买了", "取消掉"],
    "R102": ["已经寄出", "在路上", "不想收了", "别送了", "送回去"],
    "R103": ["不满意", "能退钱", "不合适", "买错了", "不想要这个"],
    # 二、物流异常
    "R201": ["没拿到", "没看见", "放哪了", "显示签收"],
    "R202": ["没动静", "一动不动", "停在半路", "物流停", "好几天没动"],
    "R203": ["丢件", "弄丢了", "包裹没了", "找不到包裹"],
    # 三、商品质量与发错
    "R301": ["有问题", "没声音", "用不了", "故障", "质量问题", "坏的"],
    "R302": ["少了一件", "数量不对", "少了东西", "没给齐"],
    "R303": ["发错了", "不是我买的", "拿错", "给错"],
    # 四、虚拟商品
    "R401": ["打不开", "链接失效", "没发给我", "网盘链接", "下不了"],
    "R402": ["不想学了", "已经看了", "学过一半", "听过了", "已经打开过"],
    "R403": ["跟描述不一样", "和页面不符", "不是宣传的样子"],
    # 五、发票与其他
    "R501": ["要发票", "开张发票", "报销"],
    "R502": ["发票改了", "抬头写错", "发票信息错"],
    "R503": ["便宜点", "能少点", "有优惠吗", "打折", "降了"],
}

# 规则未覆盖时给客服的澄清话术，把一次无效的「转人工」变成一次有效澄清
FOLLOW_UP_QUESTION = "想先确认一下：这是商品问题、物流问题，还是退款 / 发票问题？"

# 模型判定为「必须人工」时的统一答复（与 R000 口径一致）
ESCALATE_RESULT = {
    "rule_id": "R000",
    "category": "转人工 · 争议与授权",
    "advice": "此问题涉及赔付、投诉或例外承诺，AI 不给出结论性答复，请转交人工主管处理。",
    "basis": "R000-1 涉及赔偿与例外承诺必须人工授权；R000-2 投诉升级类问题不得由 AI 直接回复。",
    "need_info": [],
    "escalate": True,
    "confidence": "高",
}


def _rule_by_id(rule_id):
    for rule in RULES:
        if rule["id"] == rule_id:
            return rule
    return None


def _result_from_rule(rule, reason, confidence="中", need_info=None):
    if need_info is None:
        need_info = rule["need_info"]
    return {
        "rule_id": rule["id"],
        "category": rule["category"],
        "advice": rule["advice"],
        "basis": rule["basis"],
        "need_info": list(need_info),
        "escalate": bool(rule["escalate"]),
        "reason": reason,
        "confidence": confidence,
    }


def _synonym_match(text):
    """同义词兜底：取命中的最长短语；同长度时按规则顺序。"""
    best = None
    for rule_id, phrases in SYNONYMS.items():
        for phrase in phrases:
            if phrase in text and (best is None or len(phrase) > len(best[1])):
                best = (rule_id, phrase)
    return best


def _llm_attempt(question, product_type, order_info):
    """调分类层。返回 {"status": ok|unavailable|error, "data": dict|None}。"""
    try:
        import llm_classifier
    except Exception:
        return {"status": "unavailable", "data": None}
    if not llm_classifier.available():
        return {"status": "unavailable", "data": None}
    try:
        data = llm_classifier.classify(
            question, RULES, product_type=product_type, order_info=order_info
        )
    except Exception:
        return {"status": "error", "data": None}
    if not data:
        return {"status": "error", "data": None}
    return {"status": "ok", "data": data}


def _decorate(result, source, llm_status, follow_up=None):
    result = dict(result)
    result["source"] = source
    result["llm_status"] = llm_status
    result["follow_up"] = list(follow_up or [])
    return result


def analyze(question, product_type="未知", order_info="", mode="auto"):
    """V2 分析入口：规则 → 模型 → 同义词 → 转人工。

    Args:
        question: 客户原话。
        product_type: 商品类型。
        order_info: 订单与交付情况。
        mode: "auto" 默认（规则优先、模型兜底、同义词最后）
              "rules" 只跑 V1 规则（对照实验用）
              "llm" 规则优先、禁同义词（测模型真实能力）
    Returns:
        dict：rule_id / category / advice / basis / need_info / escalate /
              reason / confidence / source / llm_status / follow_up
    """
    base = _analyze_v1(question, product_type=product_type, order_info=order_info)

    # 规则层已经有结论（命中规则，或命中转人工关键词，或空输入）→ 直接用
    rule_missed = base["rule_id"] == "-" and base["escalate"] and base["category"] != "输入为空"
    if not rule_missed:
        source = "规则关键词" if base["rule_id"] != "-" else "—"
        return _decorate(base, source, "skipped")

    # ---------------- 第 2 层：模型意图分类 ----------------
    llm_status = "disabled" if mode == "rules" else "skipped"
    if mode in ("auto", "llm"):
        attempt = _llm_attempt(question, product_type, order_info)
        llm_status = attempt["status"]
        data = attempt["data"]
        if llm_status == "ok" and data:
            if data["escalate"]:
                result = dict(ESCALATE_RESULT)
                result["reason"] = "模型判定需人工：" + (data["reason"] or "涉及争议或授权")
                return _decorate(result, "模型", llm_status,
                                 ["涉及赔付 / 投诉的问题不要自行回复，先转主管。"])
            rule = _rule_by_id(data["rule_id"])
            if rule is not None:
                need_info = list(rule["need_info"])
                for item in data["missing"]:
                    if item not in need_info:
                        need_info.append(item)
                confidence = "高" if data["confidence"] >= 0.7 else "中"
                reason = "模型分类（{0:.2f}）：{1}".format(
                    data["confidence"], data["reason"] or rule["category"]
                )
                return _decorate(
                    _result_from_rule(rule, reason, confidence, need_info),
                    "模型", llm_status,
                )
            # 模型也给了 UNKNOWN → 继续往下走
            llm_status = "error"

    # ---------------- 第 3 层：同义词兜底（只在默认 auto 模式下启用） ----------------
    if mode == "auto":
        hit = _synonym_match(_all_text(question, product_type, order_info))
        if hit:
            rule = _rule_by_id(hit[0])
            reason = "同义词兜底命中「{0}」→ {1}".format(hit[1], hit[0])
            return _decorate(_result_from_rule(rule, reason, "中"), "同义词", llm_status)

    # ---------------- 第 4 层：转人工，并给一句澄清话术 ----------------
    reason_map = {
        "unavailable": "未配置 DeepSeek 密钥",
        "error": "模型调用失败或无法判定",
        "skipped": "未调用模型",
        "disabled": "已关闭模型",
    }
    result = dict(base)
    result["reason"] = base["reason"] + "（" + reason_map.get(llm_status, llm_status) + "）"
    return _decorate(result, "—", llm_status, [FOLLOW_UP_QUESTION])
