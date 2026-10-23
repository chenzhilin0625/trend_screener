#encoding:gbk
#code ver 1.53

'''
【使用协议】
 本策略代码由机器自动生成，云飞量化、迅投
 QMT软件开发商、证券公司均不作为投资建议方，
 不对策略效果和网络及软件系统的稳定做任何承诺，
 参考或使用本代码所带来的收益和风险均由用户自行承担。
 复制本代码表示您已理解并同意以上协议；
 若不同意，请勿复制使用，或做删除处理。
'''

import time
import re
import sys
import os
import random
import requests
from urllib.parse import quote, unquote

class G(): pass

g = G()

def init(ContextInfo):
	g.acc_id = '111'
	g.init_fund = 500000 #初始资金
	g.yfuser = '86969y'
	g.yftoken = 'E5F5DCD7684248C1D8E8FCAD'
	g.yfclid = 'b12004'
	g.yfclname = 'B4_宽基轮动及时版四'
	g.delays_trade = -1 #延时交易, -1表示随机
	g.worktime = '09:32:00-14:58:00' #工作时间
	g.commission = float(1.0) #佣金万1，本佣金率仅用于策略内部资金计算
	g.price_lv_n = 0 #报单价, 0表示自动, 1-5表示盘口对方价档次
	g.lst_skip = [] #跳过的品种：账户统一逆回购或余额理财
	g.lst_etf = { #交易的具体品种, 持仓时修改将导致无法自动卖出
		"上证50" : "510050.SH",
		"沪深300" : "510300.SH",
		"科创50" : "588000.SH",
		"中证1000" : "512100.SH",
		"中证500" : "510500.SH",
		"创业板指" : "159915.SZ",
		"创成长" : "159967.SZ",
		"深证100" : "159901.SZ",
		"创业板50" : "159949.SZ"
	}
	g.days_log_saved = 15 #策略日志文件保存天数：QMT安装目录\_mylogs
	g.yfurl = 'http://www.ycyflh.com/api'
	mc = re.match('^(\d{2}):(\d{2}):(\d{2})-(\d{2}):(\d{2}):(\d{2})$', g.worktime)
	if mc:
		g.worktime_s = int(mc.group(1) + mc.group(2) + mc.group(3))
		g.worktime_e = int(mc.group(4) + mc.group(5) + mc.group(6))
		append_log('本策略将在%s:%s:%s开始计算和交易 (%s:%s:%s之前启动有效)'
			% (mc.group(1), mc.group(2), mc.group(3), mc.group(4), mc.group(5), mc.group(6)))
		lst_acct = get_trade_detail_data(g.acc_id, 'stock', 'account')
		if len(lst_acct) == 1:
			save_his_state('workstate', '0')
		else:
			append_log('证券账号 %s 无效，本策略无法启动！' % g.acc_id)
			save_his_state('workstate', '2')
			return
	else:
		append_log('配置错误：g.worktime=%s' % g.worktime)
		save_his_state('workstate', '2')
		return
	save_his_state('tick_last', str(time.time()))
	request_data()
	ContextInfo.run_time("myhandlebar", "10nSecond", "1990-05-25 09:30:00")

def handlebar(ContextInfo):
	pass

def myhandlebar(ContextInfo):
	tick_cur = time.time()
	tick_last = float(get_his_state('tick_last', '^\d+(\.\d+)?$', '0'))
	if tick_cur - tick_last < 5:
		return
	save_his_state('tick_last', str(tick_cur))
	workstate = int(get_his_state('workstate', '^[012]$', '0'))
	if workstate != 0 and workstate != 1:
		append_log('workstate=%s, 策略已异常退出, 请人工接管！' % workstate)
		return
	tick_cur_1000 = tick_cur * 1000
	yymmdd = timetag_to_datetime(tick_cur_1000, '%Y-%m-%d')
	hhmmss = int(timetag_to_datetime(tick_cur_1000, '%H%M%S'))
	if hhmmss >= 92500 and (hasattr(g, 'work_date_last') == False or g.work_date_last != yymmdd):
		if workstate == 0 and request_data():
			list_etfs = list()
			for index_name in g.lst_etf:
				list_etfs.append(g.lst_etf[index_name])
			flag_ok = True
			df = ContextInfo.get_full_tick(list_etfs)
			for k in list_etfs:
				if k not in df:
					flag_ok = False
					append_log('【网络异常】无法连接到交易服务器，获取%s的价格数据失败，请检查交易品种配置以及QMT的网络连接！' % k)
			if flag_ok:
				append_log('%s 初始化成功！(%sv1.53)' % (g.yfclname, g.yfclid))
		g.work_date_last = yymmdd
		clear_his_log()
		return
	if hhmmss < g.worktime_s or hhmmss > g.worktime_e:
		return
	if hhmmss < 93000:
		if workstate == 1:
			append_log('尚未开盘, 交易操作开盘后操作…')
		return
	if hhmmss > 145800:
		if workstate == 1:
			append_log('已收盘，交易未能完成，请人工接管！')
		return
	if hhmmss > 113000 and hhmmss < 130000:
		if workstate == 1:
			append_log('中午休市, 交易操作开盘后继续…')
		return
	if workstate == 0:
		if request_data() == False:
			return
		if g.plan_time <= g.plan_time_last:
			return
		if yymmdd not in g.plan_time:
			append_log('【非今日指令】[%s] %s' % (g.plan_time, g.plan_text))
			return
		save_his_state('workstate', '1')
		append_log('【开始调仓】[%s] %s' % (g.plan_time, g.plan_text))
		dict_orders = dict()
		plan_arr = g.plan_text.split(';')
		for plan in plan_arr:
			if len(plan) < 2:
				continue
			if plan.find('继续') != -1:
				append_log('跳过 [%s]' % plan)
				continue
			index_name = ''
			desc_vol = float(-1)
			mc = re.match(' *([买入卖出]+) ([A-Z0-9\u4e00-\u9fa5]+ ?[A-Z0-9\u4e00-\u9fa5]*)', plan)
			if mc:
				index_name = mc.group(2)
				if mc.group(1) == '买入':
					desc_vol = float(1)
				elif mc.group(1) == '卖出':
					desc_vol = float(0)
			else:
				mc = re.match(' *([A-Z0-9\u4e00-\u9fa5]+ ?[A-Z0-9\u4e00-\u9fa5]*) 仓位\d+\.?\d*%→(\d+\.?\d*)%', plan)
				if mc:
					index_name = mc.group(1)
					desc_vol = float(mc.group(2)) / 100
			if index_name == '' or desc_vol < 0 or desc_vol > 1:
				append_log('无法识别的操作 [%s]，请人工接管！' % plan)
				save_his_state('workstate', '2')
				return
			if index_name in g.lst_skip:
				append_log('跳过 %s' % index_name)
				continue
			if index_name not in g.lst_etf:
				append_log('无法处理的品种 %s，请人工接管！' % index_name)
				save_his_state('workstate', '2')
				return
			op_etf = g.lst_etf[index_name]
			if op_etf in dict_orders:
				dict_orders[op_etf].vol_per_desc = dict_orders[op_etf].vol_per_desc + desc_vol
			else:
				dict_orders[op_etf] = OrderItem()
				dict_orders[op_etf].vol_per_desc = desc_vol
			append_log('%s %s 目标仓位 %f' % (mc.group(1), op_etf, dict_orders[op_etf].vol_per_desc))
		append_log('【缓存的历史仓位数据 - 调仓前】')
		append_log(g.my_data)
		append_log('===' * 10)
		if trade_init(dict_orders, ContextInfo) == False:
			return
		append_log('【执行调仓】')
		delays_trade_this = g.delays_trade if g.delays_trade >= 0 else random.randint(1, 20)
		if delays_trade_this > 0:
			tick_tmp = time.time() + delays_trade_this - 4
			hhmmss_tmp = int(timetag_to_datetime(tick_tmp * 1000, "%H%M%S"))
			if hhmmss_tmp > 145500:
				hh_tmp = hhmmss_tmp // 10000
				mm_tmp = (hhmmss_tmp - hh_tmp * 10000) // 100
				ss_tmp = hhmmss_tmp % 100
				tick_tmp = tick_tmp - ((hh_tmp * 60 * 60 + mm_tmp * 60 + ss_tmp) - (14 * 60 * 60 + 55 * 60))
				append_log('延迟%s秒已超过14:55，修正为14:55交易' % delays_trade_this)
			else:
				append_log('延迟%s秒交易' % delays_trade_this)
			save_his_state('tick_last', str(tick_tmp))
			save_trader_state()
			return
		trade_run(ContextInfo)
		save_trader_state()
		return
	elif workstate == 1:
		append_log('交易中…')
		load_trader_state()
		trade_run(ContextInfo)
		save_trader_state()
		return

def trade_init(dict_orders, ContextInfo):
	my_data_arr = g.my_data.split('\r\n')
	available = float(my_data_arr[1])
	append_log('策略可用资金:%s' % available)
	if len(dict_orders) > 0:
		lst_acct = get_trade_detail_data(g.acc_id, 'stock', 'account')
		if len(lst_acct) != 1:
			append_log('【网络异常-交易跳出a】无法连接到交易服务器，请检查QMT的网络连接！')
			save_his_state('workstate', '0')
			return False
		acct_info = lst_acct[0]
		available2 =  acct_info.m_dAvailable
		append_log('账户实际可用资金:%s' % available2)
		if available2 < available:
			available = available2
	if len(my_data_arr) > 2:
		for i in range(2, len(my_data_arr)):
			mc = re.match('(\d{6}\.[A-Z]{2})\t(\d+)', my_data_arr[i])
			if mc:
				etf = mc.group(1)
				vol = int(mc.group(2))
				if etf not in dict_orders:
					dict_orders[etf] = OrderItem()
					dict_orders[etf].trade = False
				dict_orders[etf].vol_hold = vol
				df = ContextInfo.get_full_tick([etf])
				if etf in df:
					dict_orders[etf].price = round(df[etf]['lastPrice'], 3)
				else:
					append_log('【网络异常-交易跳出b】无法连接到交易服务器，请检查QMT的网络连接！')
					save_his_state('workstate', '0')
					return False
	market_value_sum = 0.0
	for k in dict_orders:
		item = dict_orders[k]
		item.market_value = round(item.vol_hold * item.price, 3)
		append_log(' %s %s * %s = %s' % (k, item.vol_hold, item.price, item.market_value))
		market_value_sum = market_value_sum + item.market_value
	market_value_sum = round(market_value_sum, 3)
	append_log('策略持仓市值:%s' % market_value_sum)
	balance = available + market_value_sum
	append_log('策略总资产:%s' % balance)
	if balance <= 0:
		append_log('【策略总资产为0】请清空缓存并重新配置策略！！！')
		for k in dict_orders:
			dict_orders[k].trade = False
	else:
		append_log('【调仓任务】')
		for k in dict_orders:
			item = dict_orders[k]
			if item.trade == False:
				continue
			item.vol_per_src = item.market_value / balance
			if item.vol_per_desc > item.vol_per_src:
				item.isbuy = True
				item.amount_need_buy = round((item.vol_per_desc - item.vol_per_src) * balance, 3)
				item.amount_bought = float(0.0)
				append_log('%s 原仓位%s 原持有%s股 目标仓位%s 本次买入%s元' 
					% (k, item.vol_per_src, item.vol_hold, item.vol_per_desc, item.amount_need_buy))
			elif item.vol_per_desc < item.vol_per_src:
				item.isbuy = False
				if item.vol_per_desc <= 0:
					item.vol_hold_after_sell = 0
				else:
					item.vol_hold_after_sell = int((balance * item.vol_per_desc) / item.price / 100) * 100
				append_log('%s 原仓位%s 原持有%s股 目标仓位%s 本次卖出%s股' 
					% (k, item.vol_per_src, item.vol_hold, item.vol_per_desc, item.vol_hold - item.vol_hold_after_sell))
			else:
				item.trade = False
	g.trade_order_timeout = random.randint(30, 60)
	g.trade_available = available
	g.trade_dict_orders = dict_orders
	return True

def trade_run(ContextInfo):
	all_completed = True
	for k in g.trade_dict_orders:
		item = g.trade_dict_orders[k]
		if item.trade == False:
			continue
		if item.completed == True:
			continue
		all_completed = False
		if item.order_id == '-1':
			df = ContextInfo.get_instrumentdetail(k)
			upStopPrice = df['UpStopPrice']
			downStopPrice = df['DownStopPrice']
			price_curr_use = float()
			df = ContextInfo.get_full_tick([k])
			if k in df:
				df = df[k]
			else:
				append_log('【网络异常-交易跳出c】无法连接到交易服务器，请检查QMT的网络连接！')
				save_his_state('workstate', '2')
				return
			lastPrice = round(df['lastPrice'], 3)
			append_log('%s 现价:%s 涨停价:%s 跌停价:%s' % (k, lastPrice, upStopPrice, downStopPrice))
			if item.order_number == 1 and g.price_lv_n >= 1 and g.price_lv_n <= 5:
				price_lv_arr = df['askPrice'] if item.isbuy else df['bidPrice']
				for idx in range(g.price_lv_n, 0, -1):
					price_var = round(price_lv_arr[idx - 1], 3)
					if price_var > 0:
						price_curr_use = price_var
						break
			if price_curr_use == 0.0:
				if item.isbuy:
					if item.order_number > 1:
						price_curr_use = round(lastPrice * (1 + (item.order_number - 1) / 100), 3)
					else:
						price_curr_use = round(lastPrice * 1.002, 3)
						if price_curr_use - lastPrice < 0.002:
							price_curr_use = round(lastPrice + 0.002, 3)
						if price_curr_use - lastPrice > 0.01:
							price_curr_use = round(lastPrice + 0.01, 3)
					if price_curr_use > upStopPrice:
						price_curr_use = upStopPrice
				else:
					if item.order_number > 1:
						price_curr_use = round(lastPrice * (1 - (item.order_number - 1) / 100), 3)
					else:
						price_curr_use = round(lastPrice * 0.998, 3)
						if lastPrice - price_curr_use < 0.002:
							price_curr_use = round(lastPrice - 0.002, 3)
						if lastPrice - price_curr_use > 0.01:
							price_curr_use = round(lastPrice - 0.01, 3)
					if price_curr_use < downStopPrice:
						price_curr_use = downStopPrice
			list_order_ids = list()
			order_list = get_trade_detail_data(g.acc_id, 'stock', 'order', g.yfclid)
			for order_obj in order_list:
				list_order_ids.append(order_obj.m_strOrderSysID)
			if item.isbuy:
				item.completed = item.amount_need_buy <= 0 or item.amount_bought / item.amount_need_buy > 0.98
				if item.completed:
					append_log('【成交完成a】买入 %s 本次需买入%s元 实际买入%s元' % (k, item.amount_need_buy, item.amount_bought))
					continue
				amount_need_var = item.amount_need_buy - item.amount_bought
				amount_var = amount_need_var
				comm_tmp = amount_var / 10000 * g.commission
				item.vol_curr_order = int((amount_var - comm_tmp) / price_curr_use / 100) * 100
				item.completed = item.vol_curr_order < 100
				if item.completed:
					append_log('【成交完成b】买入 %s 本次需买入%s元 实际买入%s元' % (k, item.amount_need_buy, item.amount_bought))
					continue
				item.vol_curr_order = 0
				if g.trade_available < amount_var:
					amount_var = g.trade_available
				comm_tmp = amount_var / 10000 * g.commission
				if amount_var - comm_tmp > price_curr_use * 100:
					item.vol_curr_order = int((amount_var - comm_tmp) / price_curr_use / 100) * 100
					if item.vol_curr_order > 1000000:
						item.vol_curr_order = 1000000
				if item.vol_curr_order < 1000000:
					if item.vol_curr_order < 100 or (amount_var < amount_need_var * 0.5):
						append_log('【买入%s资金不足, 等待其他卖单成交后继续】需买入:%s 已买入:%s 还需买入:%s 可用:%s' 
							% (k, item.amount_need_buy, item.amount_bought, amount_need_var, g.trade_available))
						flag_sell_allcompleted = True
						for k2 in g.trade_dict_orders:
							item2 = g.trade_dict_orders[k2]
							if item2.trade == True and item2.isbuy == False and item2.completed == False:
								flag_sell_allcompleted = False
								break
						if flag_sell_allcompleted:
							append_log('【所有卖单均已成交】重置需买入%s的资金为:%s' % (k, item.amount_bought))
							item.amount_need_buy = item.amount_bought
							if item.amount_need_buy <= 0:
								append_log('需买入资金可能不正常，请人工核实或人工接管！')
						continue
				append_log('【%d 挂买单 %s】%s * %s' % (item.order_number, k, price_curr_use, item.vol_curr_order))
				passorder(23, 1101, g.acc_id, k, 11, price_curr_use, item.vol_curr_order, g.yfclid, 2, '', ContextInfo)
				item.order_updown_stop = price_curr_use >= upStopPrice
				item.order_number = item.order_number + 1
			else:
				item.vol_curr_order = item.vol_hold - item.vol_hold_after_sell
				item.completed = item.vol_curr_order < 100
				if item.completed:
					append_log('【成交完成c】卖出 %s' % k)
					continue
				if item.vol_curr_order > 1000000:
					item.vol_curr_order = 1000000
				append_log('【%d 挂卖单 %s】%s * %s' % (item.order_number, k, price_curr_use, item.vol_curr_order))
				passorder(24, 1101, g.acc_id, k, 11, price_curr_use, item.vol_curr_order, g.yfclid, 2, '', ContextInfo)
				item.order_updown_stop = price_curr_use <= downStopPrice
				item.order_number = item.order_number + 1
			item.order_time = time.time()
			flag_ok = False
			order_id_var = '-1'
			for i in range(20):
				time.sleep(0.5)
				order_list = get_trade_detail_data(g.acc_id, 'stock', 'order', g.yfclid)
				for order_obj in order_list:
					order_id_var = order_obj.m_strOrderSysID
					if order_id_var in list_order_ids:
						continue
					if re.match('^[\d_]+$', order_id_var) == None:
						continue
					item.order_id = order_id_var
					flag_ok = True
					append_log('委托编号 %s' % item.order_id)
					break
				if flag_ok == True:
					break
				elif i == 19:
					n = 1
					for order_obj in order_list:
						append_log('order_%d:%s [%s] %s' % (n, order_obj.m_strOrderSysID, order_obj.m_nOrderStatus, order_obj.m_strCancelInfo))
						n = n + 1
			if flag_ok == False:
				append_log(list_order_ids)
				append_log('获取委托编号失败！请立即人工接管！')
				save_his_state('workstate', '2')
				return
		else:
			deal_vol = 0
			deal_amount = float()
			deal_list = get_trade_detail_data(g.acc_id, 'stock', 'deal', g.yfclid)
			for deal_obj in deal_list:
				if (deal_obj.m_strOrderSysID != item.order_id):
					continue
				deal_vol = deal_vol + deal_obj.m_nVolume
				deal_amount = round(deal_amount + deal_obj.m_dTradeAmount, 3)
			if deal_vol < item.vol_curr_order:
				append_log('【部分成交 %s 股数 %s; 金额 %s; 委托ID %s】' % (k, deal_vol, deal_amount, item.order_id))
				if item.order_updown_stop:
					append_log('但因挂在涨跌停价上，不做撤单，继续等待成交…')
					continue
				elif time.time() - item.order_time < g.trade_order_timeout:
					append_log('委托暂未超时，继续等待，暂不撤单…')
					continue
				else:
					append_log('【撤单】委托ID: %s' % item.order_id)
					cancel(item.order_id, g.acc_id, 'stock', ContextInfo)
					time.sleep(5)
					deal_vol = 0
					deal_amount = float()
					deal_list = get_trade_detail_data(g.acc_id, 'stock', 'deal', g.yfclid)
					for deal_obj in deal_list:
						if (deal_obj.m_strOrderSysID != item.order_id):
							continue
						deal_vol = deal_vol + deal_obj.m_nVolume
						deal_amount = round(deal_amount + deal_obj.m_dTradeAmount, 3)
			comm_var = deal_amount / 10000 * g.commission
			if item.isbuy:
				append_log('【买入%s】委托%s股; 成交%s股; 成交额%s; 委托ID %s' % (k, item.vol_curr_order, deal_vol, deal_amount, item.order_id))
				item.vol_hold = item.vol_hold + deal_vol
				item.amount_bought = item.amount_bought + deal_amount + comm_var
				g.trade_available = g.trade_available - deal_amount - comm_var
			else:
				append_log('【卖出%s】委托%s股; 成交%s股; 成交额%s; 委托ID %s' % (k, item.vol_curr_order, deal_vol, deal_amount, item.order_id))
				item.vol_hold = item.vol_hold - deal_vol
				g.trade_available = g.trade_available + deal_amount - comm_var
			item.order_id = '-1'
	if all_completed == False:
		return
	save_his_state('workstate', '0')
	append_log('== 调仓完成 ==')
	if g.trade_available < 0:
		append_log('行情波动至可用资金[%s] 小于0，校正为0' % g.trade_available)
		g.trade_available = 0
	g.my_data = g.plan_time + '\r\n' + str(round(g.trade_available, 3))
	for k in g.trade_dict_orders:
		item = g.trade_dict_orders[k]
		if item.vol_hold > 0:
			g.my_data = g.my_data + '\r\n' + k + '\t' + str(item.vol_hold)
	append_log('【调仓后的仓位数据】')
	append_log(g.my_data)
	append_log('===' * 10)
	if update_mydata(g.my_data):
		append_log('仓位数据保存成功!')
	if 'b12' not in g.yfclid:
		tick_tmp = time.time()
		hhmmss_tmp = int(timetag_to_datetime(tick_tmp * 1000, "%H%M%S"))
		hh_tmp = hhmmss_tmp // 10000
		mm_tmp = (hhmmss_tmp - hh_tmp * 10000) // 100
		ss_tmp = hhmmss_tmp % 100
		tick_tmp = tick_tmp + ((16 * 60 * 60) - (hh_tmp * 60 * 60 + mm_tmp * 60 + ss_tmp))
		save_his_state('tick_last', str(tick_tmp))

def request_data():
	try:
		url = '%s?user=%s&token=%s&m=1&id=%s&%s' % (g.yfurl, g.yfuser, g.yftoken, g.yfclid, time.time())
		request = requests.get(url)
		request.encoding = "utf-8"
		js = request.json()
		if 'errcode' in js:
			if js['errcode'] != 1006:
				append_log(js)
			return False
		cl_name = js[0]['策略名']
		plan_time = js[0]['调仓时间']
		if re.match('^\d+-\d+-\d+ \d+:\d+$', plan_time) == None:
			append_log('无法识别的调仓时间：%s' % plan_time)
			return False
		plan_text = js[0]['调仓方案']
		my_data = unquote(js[0]['自定义数据'], 'utf-8')
		mc = re.match('^(\d+-\d+-\d+ \d+:\d+)\r\n\d+\.?\d*(\r\n\d{6}\.[A-Z]{2}\t\d+)*$', my_data)
		plan_time_last_var = ''
		if mc:
			plan_time_last_var = mc.group(1)
		else:
			plan_time_last_var = plan_time
			append_log('历史仓位数据[%s]为空或格式无效，判断为首次开启策略，自动初始化为[上次调仓时间:%s; 可用资金:%s]' % (my_data, plan_time, g.init_fund))
			my_data = plan_time + '\r\n' + str(g.init_fund)
			if update_mydata(my_data) == False:
				return False
		if hasattr(g, 'plan_time_last') == False:
			append_log('启动 %s，上次已处理调仓时间: %s' % (cl_name, plan_time_last_var))
			append_log('【缓存的历史仓位数据】')
			append_log(my_data)
			append_log('===' * 10)
		g.plan_time_last = plan_time_last_var
		g.plan_time = plan_time
		g.plan_text = plan_text
		g.my_data = my_data
		return True
	except:
		append_log("requestdata ERROR:%s" % sys.exc_info())
		return False

def update_mydata(my_data):
	my_data_quote = quote(my_data, 'utf-8')
	url = '%s?user=%s&token=%s&m=2&id=%s&data=%s' % (g.yfurl, g.yfuser, g.yftoken, g.yfclid, my_data_quote)
	js = ''
	for i in range(10):
		try:
			request = requests.get(url)
			request.encoding = "utf-8"
			js = request.json()
			if 'errcode' in js and js['errcode'] == 0:
				return True
		except:
			pass
		time.sleep(1)
	append_log(js)
	append_log(url)
	append_log('仓位数据保存失败！')
	return False

def get_his_state(k, pattern, dft):
	filename = "%s\\_myfiles\\%s_%s.txt" % (os.getcwd(), g.yfclid, k)
	if os.path.exists(filename):
		fs = open(filename, 'r')
		txtbfr = fs.readline()
		fs.close()
		mc = re.match(pattern, txtbfr)
		if mc:
			return txtbfr
	return dft

def save_his_state(k, vlu):
	filename = "%s\\_myfiles" % os.getcwd()
	if not os.path.exists(filename):
		os.mkdir(filename)
	filename = "%s\\%s_%s.txt" % (filename, g.yfclid, k)
	with open(filename, 'w') as fs:
		fs.write(vlu)

def load_trader_state():
	g.plan_time = get_his_state('plan_time', '^.*$', '')
	g.trade_order_timeout = int(get_his_state('trade_order_timeout', '^\d{2}$', '60'))
	g.trade_available = float(get_his_state('trade_available', '^[\d\.\-]*$', '0'))
	dict_orders = dict()
	strtmp = get_his_state('trade_dict_orders', '^.*$', '')
	arr0 = strtmp.split('$')
	for line in arr0:
		arr1 = line.split(';')
		if len(arr1) == 2:
			dict_orders[arr1[0]] = OrderItem().FromString(arr1[1])
	g.trade_dict_orders = dict_orders

def save_trader_state():
	save_his_state('plan_time', g.plan_time)
	save_his_state('trade_order_timeout', str(g.trade_order_timeout))
	save_his_state('trade_available', str(g.trade_available))
	strtmp = ''
	for k in g.trade_dict_orders:
		if strtmp != '':
			strtmp = strtmp + '$'
		strtmp = strtmp + k + ';' + g.trade_dict_orders[k].ToString()
	save_his_state('trade_dict_orders', strtmp)

class OrderItem:
	trade = True
	vol_hold = 0
	price = float()
	market_value = float()
	vol_per_src = float()
	vol_per_desc = float()
	isbuy = False
	amount_need_buy = float()
	amount_bought = float()
	vol_hold_after_sell = 0
	vol_curr_order = 0
	order_number = 1
	order_id = '-1'
	order_time = float()
	order_updown_stop = False
	completed = False
	def ToString(self):
		str = '{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}'
		return str.format(int(self.trade),self.vol_hold,self.price,self.market_value,self.vol_per_src,self.vol_per_desc,int(self.isbuy),self.amount_need_buy,self.amount_bought,self.vol_hold_after_sell,self.vol_curr_order,self.order_number,self.order_id,self.order_time,int(self.order_updown_stop),int(self.completed))
	def FromString(self, str):
		arr = str.split('|')
		self.trade = bool(int(arr[0]))
		self.vol_hold = int(arr[1])
		self.price = float(arr[2])
		self.market_value = float(arr[3])
		self.vol_per_src = float(arr[4])
		self.vol_per_desc = float(arr[5])
		self.isbuy = bool(int(arr[6]))
		self.amount_need_buy = float(arr[7])
		self.amount_bought = float(arr[8])
		self.vol_hold_after_sell = int(arr[9])
		self.vol_curr_order = int(arr[10])
		self.order_number = int(arr[11])
		self.order_id = arr[12]
		self.order_time = float(arr[13])
		self.order_updown_stop = bool(int(arr[14]))
		self.completed = bool(int(arr[15]))
		return self

def append_log(log):
	print(log)
	pathname = "%s\\_mylogs" % os.path.dirname(os.getcwd())
	if not os.path.exists(pathname):
		os.mkdir(pathname)
	tick_cur = time.time() * 1000
	filename = "%s\\%s %s.txt" % (pathname, timetag_to_datetime(tick_cur, '%Y-%m-%d'), g.yfclname)
	with open(filename, 'a') as fs:
		fs.write("[%s] %s\n" % (timetag_to_datetime(tick_cur, '%m-%d %H:%M:%S'), log.replace("\r\n", "\n") if isinstance(log, str) else log))

def clear_his_log():
	current_timestamp = time.time()
	n_days_in_seconds = g.days_log_saved * 24 * 3600
	pathname = "%s\\_mylogs" % os.path.dirname(os.getcwd())
	files = os.listdir(pathname)
	for filename in files:
		mc = re.match('^(\d{4}-\d+-\d+) .*\.txt$', filename)
		if mc:
			date_str = mc.group(1)
			date_timestamp = time.mktime(time.strptime(date_str, '%Y-%m-%d'))
			if current_timestamp - date_timestamp > n_days_in_seconds:
				os.remove("%s\\%s" % (pathname, filename))