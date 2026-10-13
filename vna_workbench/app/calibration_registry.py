"""Workflow choices; only VMC currently has a numerical implementation."""

CALIBRATION_TYPES = {
    'vmc': ('VMC · 矢量混频器校准', '频率变换'),
    'smc': ('SMC · 标量混频器校准', '频率变换'),
    'response': ('Response · 响应校准', '基础 S 参数'),
    'enhanced_response': ('Enhanced Response · 增强响应', '基础 S 参数'),
    'sol': ('SOL / OSM · 单端口校准', '基础 S 参数'),
    'solt': ('SOLT · 双端口校准', '基础 S 参数'),
    'qsolt': ('QSOLT · 快速 SOLT', '基础 S 参数'),
    'solr': ('SOLR / Unknown Thru', '基础 S 参数'),
    'trl': ('TRL · 传输线校准', '传输线'),
    'trm': ('TRM · 传输线校准', '传输线'),
    'lrm': ('LRM / LRL · 传输线校准', '传输线'),
    'multiline_trl': ('Multiline TRL · 多线 TRL', '传输线'),
    'power': ('功率校准', '专项工作流'),
    'multiport': ('多端口校准', '专项工作流'),
    'ecal': ('ECal · 电子校准工作流', '专项工作流'),
    'noise': ('噪声校准', '专项工作流'),
}
