"""TA-Lib 函数中文说明（替代英文 display_name 展示）。"""

from __future__ import annotations

# key = TA-Lib 函数名；value = 中文说明
TALIB_ZH_DESC: dict[str, str] = {
    # Cycle
    "HT_DCPERIOD": "希尔伯特变换：主导周期",
    "HT_DCPHASE": "希尔伯特变换：主导周期相位",
    "HT_PHASOR": "希尔伯特变换：相量分量",
    "HT_SINE": "希尔伯特变换：正弦波",
    "HT_TRENDMODE": "希尔伯特变换：趋势/周期模式",
    # Math operators
    "ADD": "向量加法",
    "DIV": "向量除法",
    "MAX": "指定周期内最高值",
    "MAXINDEX": "指定周期内最高值索引",
    "MIN": "指定周期内最低值",
    "MININDEX": "指定周期内最低值索引",
    "MINMAX": "指定周期内最低与最高值",
    "MINMAXINDEX": "指定周期内最低与最高值索引",
    "MULT": "向量乘法",
    "SUB": "向量减法",
    "SUM": "指定周期求和",
    # Math transform
    "ACOS": "反余弦",
    "ASIN": "反正弦",
    "ATAN": "反正切",
    "CEIL": "向上取整",
    "COS": "余弦",
    "COSH": "双曲余弦",
    "EXP": "自然指数",
    "FLOOR": "向下取整",
    "LN": "自然对数",
    "LOG10": "常用对数（log10）",
    "SIN": "正弦",
    "SINH": "双曲正弦",
    "SQRT": "平方根",
    "TAN": "正切",
    "TANH": "双曲正切",
    # Momentum
    "ADX": "平均趋向指数 ADX",
    "ADXR": "平均趋向指数评级 ADXR",
    "APO": "绝对价格振荡器 APO",
    "AROON": "阿隆指标 Aroon",
    "AROONOSC": "阿隆振荡器",
    "BOP": "均势指标 BOP",
    "CCI": "商品通道指数 CCI",
    "CMO": "钱德动量摆动指标 CMO",
    "DX": "动向指数 DX",
    "MACD": "异同移动平均线 MACD",
    "MACDEXT": "可配置均线类型的 MACD",
    "MACDFIX": "固定 12/26 周期的 MACD",
    "MFI": "资金流量指标 MFI",
    "MINUS_DI": "负向动向指标 −DI",
    "MINUS_DM": "负向动向值 −DM",
    "MOM": "动量 MOM",
    "PLUS_DI": "正向动向指标 +DI",
    "PLUS_DM": "正向动向值 +DM",
    "PPO": "百分比价格振荡器 PPO",
    "ROC": "变动率 ROC（百分比）",
    "ROCP": "变动率 ROCP（小数）",
    "ROCR": "变动率比值 ROCR",
    "ROCR100": "变动率比值×100",
    "RSI": "相对强弱指数 RSI",
    "STOCH": "随机指标 KD（慢速）",
    "STOCHF": "快速随机指标",
    "STOCHRSI": "随机相对强弱指标 StochRSI",
    "TRIX": "三重指数平滑变动率 TRIX",
    "ULTOSC": "终极振荡器 ULTOSC",
    "WILLR": "威廉指标 %R",
    # Overlap
    "BBANDS": "布林带 Bollinger Bands",
    "DEMA": "双指数移动平均 DEMA",
    "EMA": "指数移动平均 EMA",
    "HT_TRENDLINE": "希尔伯特变换：瞬时趋势线",
    "KAMA": "考夫曼自适应移动平均 KAMA",
    "MA": "移动平均 MA",
    "MAMA": "MESA 自适应移动平均 MAMA",
    "MAVP": "可变周期移动平均",
    "MIDPOINT": "周期中点价",
    "MIDPRICE": "最高最低中点价",
    "SAR": "抛物线转向 SAR",
    "SAREXT": "扩展抛物线转向 SAR",
    "SMA": "简单移动平均 SMA",
    "T3": "三重指数移动平均 T3",
    "TEMA": "三重指数移动平均 TEMA",
    "TRIMA": "三角移动平均 TRIMA",
    "WMA": "加权移动平均 WMA",
    # Pattern (K 线形态)
    "CDL2CROWS": "K线形态：两只乌鸦",
    "CDL3BLACKCROWS": "K线形态：三只乌鸦",
    "CDL3INSIDE": "K线形态：三内部上涨/下跌",
    "CDL3LINESTRIKE": "K线形态：三线打击",
    "CDL3OUTSIDE": "K线形态：三外部上涨/下跌",
    "CDL3STARSINSOUTH": "K线形态：南方三星",
    "CDL3WHITESOLDIERS": "K线形态：三白兵",
    "CDLABANDONEDBABY": "K线形态：弃婴",
    "CDLADVANCEBLOCK": "K线形态：大敌当前",
    "CDLBELTHOLD": "K线形态：捉腰带线",
    "CDLBREAKAWAY": "K线形态：脱离",
    "CDLCLOSINGMARUBOZU": "K线形态：收盘光头光脚",
    "CDLCONCEALBABYSWALL": "K线形态：藏婴吞没",
    "CDLCOUNTERATTACK": "K线形态：反击线",
    "CDLDARKCLOUDCOVER": "K线形态：乌云盖顶",
    "CDLDOJI": "K线形态：十字星",
    "CDLDOJISTAR": "K线形态：十字星形态",
    "CDLDRAGONFLYDOJI": "K线形态：蜻蜓十字",
    "CDLENGULFING": "K线形态：吞没",
    "CDLEVENINGDOJISTAR": "K线形态：黄昏十字星",
    "CDLEVENINGSTAR": "K线形态：黄昏之星",
    "CDLGAPSIDESIDEWHITE": "K线形态：向上/下跳空并列阳线",
    "CDLGRAVESTONEDOJI": "K线形态：墓碑十字",
    "CDLHAMMER": "K线形态：锤头",
    "CDLHANGINGMAN": "K线形态：上吊线",
    "CDLHARAMI": "K线形态：母子线",
    "CDLHARAMICROSS": "K线形态：十字母子",
    "CDLHIGHWAVE": "K线形态：风高浪大线",
    "CDLHIKKAKE": "K线形态：陷阱",
    "CDLHIKKAKEMOD": "K线形态：修正陷阱",
    "CDLHOMINGPIGEON": "K线形态：家鸽",
    "CDLIDENTICAL3CROWS": "K线形态：三胞胎乌鸦",
    "CDLINNECK": "K线形态：颈内线",
    "CDLINVERTEDHAMMER": "K线形态：倒锤头",
    "CDLKICKING": "K线形态：反冲",
    "CDLKICKINGBYLENGTH": "K线形态：由较长光头决定的反冲",
    "CDLLADDERBOTTOM": "K线形态：梯底",
    "CDLLONGLEGGEDDOJI": "K线形态：长脚十字",
    "CDLLONGLINE": "K线形态：长蜡烛",
    "CDLMARUBOZU": "K线形态：光头光脚",
    "CDLMATCHINGLOW": "K线形态：相同低价",
    "CDLMATHOLD": "K线形态：铺垫",
    "CDLMORNINGDOJISTAR": "K线形态：早晨十字星",
    "CDLMORNINGSTAR": "K线形态：早晨之星",
    "CDLONNECK": "K线形态：颈上线",
    "CDLPIERCING": "K线形态：刺透",
    "CDLRICKSHAWMAN": "K线形态：黄包车夫",
    "CDLRISEFALL3METHODS": "K线形态：上升/下降三法",
    "CDLSEPARATINGLINES": "K线形态：分离线",
    "CDLSHOOTINGSTAR": "K线形态：射击之星",
    "CDLSHORTLINE": "K线形态：短蜡烛",
    "CDLSPINNINGTOP": "K线形态：纺锤",
    "CDLSTALLEDPATTERN": "K线形态：停顿",
    "CDLSTICKSANDWICH": "K线形态：条形三明治",
    "CDLTAKURI": "K线形态：探水竿（长下影蜻蜓）",
    "CDLTASUKIGAP": "K线形态：跳空并列阴阳线",
    "CDLTHRUSTING": "K线形态：插入",
    "CDLTRISTAR": "K线形态：三星",
    "CDLUNIQUE3RIVER": "K线形态：奇特三河床",
    "CDLUPSIDEGAP2CROWS": "K线形态：向上跳空两只乌鸦",
    "CDLXSIDEGAP3METHODS": "K线形态：上升/下降跳空三法",
    # Price transform
    "AVGPRICE": "平均价（开高低收均值）",
    "MEDPRICE": "中间价（最高最低均值）",
    "TYPPRICE": "典型价格（高低收均值）",
    "WCLPRICE": "加权收盘价",
    "CLOSE": "收盘价",
    "OPEN": "开盘价",
    "HIGH": "最高价",
    "LOW": "最低价",
    # Statistic
    "BETA": "贝塔系数 Beta",
    "CORREL": "皮尔逊相关系数",
    "LINEARREG": "线性回归",
    "LINEARREG_ANGLE": "线性回归角度",
    "LINEARREG_INTERCEPT": "线性回归截距",
    "LINEARREG_SLOPE": "线性回归斜率",
    "STDDEV": "标准差",
    "TSF": "时间序列预测",
    "VAR": "方差",
    # Volatility
    "ATR": "平均真实波幅 ATR",
    "NATR": "归一化平均真实波幅 NATR",
    "TRANGE": "真实波幅 True Range",
    # Volume
    "AD": "佳庆累积/派发线 A/D",
    "ADOSC": "佳庆振荡器 A/D Oscillator",
    "OBV": "能量潮 OBV",
}


def zh_desc_for_talib(talib_name: str) -> str:
    """
    返回 TA-Lib 函数的中文说明；未知则回退函数名。

    @param talib_name: TA-Lib 函数名
    """
    key = (talib_name or "").strip()
    if not key:
        return ""
    if key in TALIB_ZH_DESC:
        return TALIB_ZH_DESC[key]
    # 尝试读取英文 display_name 作为最后回退（仍无中文时至少有说明）
    try:
        from talib import abstract

        en = str(abstract.Function(key).info.get("display_name") or "").strip()
        if en:
            return en
    except Exception:  # noqa: BLE001
        pass
    return key
