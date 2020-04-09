import requests
import time
rates = {}
rates['ftx'] = {}
rates['bin'] = {}
{}
def compounding(intervals, amt, rate):
    while intervals > 0:
        intervals = intervals - 1
        amt = amt + (rate * amt)
    return amt
while True:
    binance = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex").json()  
    for rate in binance:
        rates['bin'][rate['symbol'].replace('USDT', '')] = float(rate['lastFundingRate']) * 3
    ftx = requests.get("https://ftx.com/api/funding_rates").json()['result']
    
    for rate in ftx:
        rates['ftx'][rate['future'].replace('-PERP', '')] = rate['rate'] * 24

    coins = {}
    coins['ftx'] = {}
    coins['bin'] = {}    
    
    for ex in rates:
        for rate in rates[ex]:
            coins[ex][rate] = rates[ex][rate]

    arbs = {}
    arbsf = {}
    for coin in coins:
        for fut in coins[coin]:
            arbs[fut] = {}
    for coin in coins:
        for fut in coins[coin]:
            arbs[fut][coin] = coins[coin][fut]
    print('arb now')
    arbsmult = []
    for arb in arbs:
        if len(arbs[arb]) > 1:
            binance = arbs[arb]['bin']
            ftx = arbs[arb]['ftx']
            if ftx < binance and ftx <=0 and binance >= 0 and ftx != binance:
                arbsmult.append({'coin': arb, 'long': 'ftx', 'short': 'binance', 'arb': binance - ftx})
            if ftx > binance and ftx >=0 and binance <= 0 and ftx != binance:
                arbsmult.append({'coin': arb, 'long': 'binance', 'short': 'ftx', 'arb': ftx - binance})
    t = 0
    c = 0
    bal = 500
    lev = 5
    exposure = bal * lev
    fees = (0.02/100 + (0.02*0.7)/100) * 2
    for arb in arbsmult:
        t = t + arb['arb']
        c = c + 1
    tdaily = 0
    test = 0
    for arb in arbsmult:
        arb['perc'] = round(arb['arb'] / t * 1000) / 1000
        arb['amt'] = round(exposure * arb['perc'] * 1000) / 1000
        arb['daily'] = round(arb['amt'] * arb['arb'] * 1000) / 1000
        test = test + arb['daily']
        
        arb['daily fees'] = arb['daily'] * fees
        arb['daily - fees'] = arb['daily'] - arb['daily fees']
        tdaily = tdaily + arb['daily - fees']
    returns = round((tdaily / bal) * 1000000) / 10000
    print('assuming $' + str(bal) + ' balance and ' + str(lev) + 'x leverage, and ' + str(fees * 100) + '% fees for a roundtrip as maker to buy/sell the exposure: ')
    print(arbsmult)
    print('that would be ' + str(returns) + '% daily returns')
    annualret = (compounding(365, bal, returns / 100) * 1000) / 1000
    roe = ((((annualret / bal) * 1000) / 10) * 1000) / 1000
    apr = (returns * 365 * 1000) / 1000
    print('that is $' + str(annualret) + ' annualized, ' + str(roe) + '% ROE and ' + str(apr) + '% APR')
 
