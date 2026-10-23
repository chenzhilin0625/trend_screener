"""一键拉取东方财富接口原始数据，展示所有字段"""
import os, time, json, requests

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']:
    os.environ.pop(k,None)
os.environ['NO_PROXY'] = '*'

BASE = 'https://push2.eastmoney.com/api/qt/clist/get'
BASE_K = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'

# ------- 1. 个股列表：最大字段集 -------
print('=' * 70)
print('1. 个股列表 (m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23)')
print('=' * 70)
r = requests.get(BASE, params={
    'pn': '1', 'pz': '2', 'po': '1', 'np': '1', 'fltt': '2', 'invt': '2',
    'fid': 'f3',
    'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
    'fields': 'f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18,'
              'f19,f20,f21,f22,f23,f24,f25,f26,f27,f28,f29,f30,f31,f32,f33,'
              'f38,f39,f40,f41,f42,f43,f44,f45,f46,f48,f49,f50,f51,f52,'
              'f100,f101,f102,f103,f104,f105,f106,f107,f108,f109,f110,f111,'
              'f112,f113,f114,f115,f116,f117,f124,f125,f128,f129,f130,f131,'
              'f132,f133,f134,f135,f136,f137,f138,f139,f140,f141,f142,f143,'
              'f144,f145,f146,f147,f148,f149,f152,f153,f169,f170,f171',
}, timeout=15)
d = r.json()
total = d.get('data',{}).get('total',0)
print(f'全市场: {total} 只')
for item in d.get('data',{}).get('diff',[]):
    for k,v in sorted(item.items()):
        print(f'  {k}: {v}')
    print(f'  --- keys: {", ".join(sorted(item.keys()))}')
    break

# ------- 2. 日线 K 线 -------
print()
print('=' * 70)
print('2. 个股日线 K 线 (000001 平安银行, 2026年7月)')
print('=' * 70)
r2 = requests.get(BASE_K, params={
    'secid': '0.000001',
    'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64',
    'klt': '101', 'fqt': '1', 'beg': '20260701', 'end': '20260720',
}, timeout=15)
d2 = r2.json()
kd = d2.get('data',{})
print(f"name: {kd.get('name')}")
print(f"code: {kd.get('code')}")
print(f"market: {kd.get('market')}")
klines = kd.get('klines',[])
if klines:
    print(f'klines: {len(klines)} 条')
    fields_part = 'f51=日期,f52=开盘,f53=收盘,f54=最高,f55=最低,f56=成交量,f57=成交额,f58=振幅,f59=涨跌幅,f60=涨跌额,f61=换手率'
    print(f'  字段: {fields_part}')
    print(f'  首条: {klines[0]}')
    print(f'  末条: {klines[-1]}')

# ------- 3. 行业板块 -------
print()
print('=' * 70)
print('3. 行业板块 (m:90+t:2)')
print('=' * 70)
r3 = requests.get(BASE, params={
    'pn': '1', 'pz': '3', 'po': '1', 'np': '1', 'fltt': '2', 'invt': '2',
    'fid': 'f3', 'fs': 'm:90+t:2',
    'fields': 'f2,f3,f4,f12,f13,f14,f15,f16,f17,f20,f21,f100,f102,f104,f105',
}, timeout=15)
d3 = r3.json()
print(f'行业板块: {d3.get("data",{}).get("total",0)} 个')
for item in d3.get('data',{}).get('diff',[]):
    for k,v in sorted(item.items()):
        print(f'  {k}: {v}')
    break

# ------- 4. 概念板块 -------
print()
print('=' * 70)
print('4. 概念板块 (m:90+t:3)')
print('=' * 70)
r4 = requests.get(BASE, params={
    'pn': '1', 'pz': '3', 'po': '1', 'np': '1', 'fltt': '2', 'invt': '2',
    'fid': 'f3', 'fs': 'm:90+t:3',
    'fields': 'f2,f3,f4,f12,f13,f14,f15,f16,f17,f20,f21',
}, timeout=15)
d4 = r4.json()
print(f'概念板块: {d4.get("data",{}).get("total",0)} 个')
for item in d4.get('data',{}).get('diff',[]):
    for k,v in sorted(item.items()):
        print(f'  {k}: {v}')
    break

# ------- 5. 个股的行业/概念标签 -------
print()
print('=' * 70)
print('5. 个股所属行业/概念 (stock_individual_info_em 模拟字段)')
print('  (东方财富个股页面包含所属行业/概念的板块ID)')
print('=' * 70)
# 用 stock_billboard 或 clist 按个股筛选行业
# f12=股票代码, 查该股属于哪些板块：fs=b:YOUR_SECTOR + f12
# 这里拉一下 000001 平安银行的信息
r5 = requests.get(BASE, params={
    'pn': '1', 'pz': '20', 'po': '1', 'np': '1', 'fltt': '2', 'invt': '2',
    'fid': 'f3',
    'fs': 'b:BK0476',  # 银行板块成分股
    'fields': 'f2,f3,f4,f12,f13,f14,f20',
}, timeout=15)
d5 = r5.json()
print(f'银行板块(BK0476): {d5.get("data",{}).get("total",0)} 只成分股')
for item in d5.get('data',{}).get('diff',[]) or []:
    print(f'  {item.get("f12")} {item.get("f14")}')

# ------- 6. 板块日线 K 线 -------
print()
print('=' * 70)
print('6. 行业板块日线 K 线 (银行 BK0476)')
print('=' * 70)
r6 = requests.get(BASE_K, params={
    'secid': '90.BK0476',
    'fields1': 'f1,f2,f3,f4,f5,f6,f7',
    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
    'klt': '101', 'fqt': '1', 'beg': '20260701', 'end': '20260720',
}, timeout=15)
d6 = r6.json()
kd6 = d6.get('data',{})
print(f"name: {kd6.get('name')}")
klines6 = kd6.get('klines',[])
if klines6:
    print(f'klines: {len(klines6)} 条')
    print(f'  首条: {klines6[0]}')
    print(f'  末条: {klines6[-1]}')

print()
print('=' * 70)
print('Done.')
