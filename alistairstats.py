import ccxt


from time import sleep
deribit     = ccxt.deribit({
            'apiKey': 'ucHSZZg7',
            'secret': 'EsKQSyuuuuiA3daw_RCeIkE5GMbj1XD-vXXQpq4bppA',
        })
print(dir(deribit))
bitmex     = ccxt.bitmex({
            'apiKey': 'sGHr0ll5Nma3kfpLc9Y6ulFZ',
            'secret': 's7AZmA4mHBaH4leAsQjRUCdy_Z-VnHRWIF1B75rm6oRMeQOs',
        })

bybit     = ccxt.bybit({
            'apiKey': 'tGLSF3rwSDkk8ScWym',
            'secret': 'fm4zTEhKBrcTetQWK0v5fNzxazsTy9d6ANKn',
        })

doneYet = []


fundingEarned = {}
fundingEarned['totalsncerun'] = 0	
while True:
	fundingEarned['binance'] = 0
	fundingEarned['totalthishour'] = 0		
	fundingEarned['ftx'] = 0		
	income = binance.fapiPrivateGetIncome({'incomeType': 'FUNDING_FEE'})
	fundingEarned['total'] = 0
	for pay in income:
		if pay['time'] not in doneYet:
			doneYet.append(pay['time'])
			fundingEarned['binance'] = fundingEarned['binance'] + float(pay['income'])




	pays = ftx.private_get_funding_payments()['result']
	for pay in pays:
		if pay['id'] not in doneYet:
			doneYet.append(pay['id'])
			amount = (ftx.fetch_ticker(pay['future']))['last'] * pay['payment'] * -1
			pay['USD Amount'] = amount
			fundingEarned['ftx'] = fundingEarned['ftx'] + pay['USD Amount']


	fundingEarned['totalsncerun'] = fundingEarned['totalsincerun']  + fundingEarned['binance'] + fundingEarned['ftx']
	fundingEarned['totalthishour'] = fundingEarned['binance'] + fundingEarned['ftx']

	print('Here are funding earnings this hour (stay tuned for huorly updates!')
	print(fundingEarned)
	sleep(60 * 60)