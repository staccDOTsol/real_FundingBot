import ccxt

from time import sleep
ftxKEY     = "E4K2syhCrHK1eIGfd2aaV9c6ee0n1qRKt1khrAHa"#os.environ["ftxkey"]#"NqOlVRaqGM-XCX0cpf67UYxvT2tcB56SHlS-tlB-"#"VC4d7Pj1"
ftxSECRET  = "r6lUTsBdqdT6HYt66RyGK5qHAE6TURW8vyhXJtR2"#os.environ["ftxsecret"]#gnBQZHa8-cT1E-p0YyNqHkx9Y_8bdk"#"IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"
binKEY     = "xRWimnhkpmr24gt12EQLYTT6TU8O1mK559E4HovZ2auP50JDtvhhQvVmaoRfCaoq"#os.environ["binkey"]#"VC4d7Pj1"
binSECRET  = "WsGLywb8ty4L3p5OWIH62ItgTRULtLvywvmIkxsVXjLVISHyNojlAt48omP3UXvb"#os.environ['binsecret']#"#"IB4VEP26O

binance     = ccxt.binance({
            'enableRateLimit': True,
            'apiKey': binKEY,
            'secret': binSECRET,
            "options":{"defaultMarket":"futures"},
            'urls': {'api': {
                                     'public': 'https://fapi.binance.com/fapi/v1',
                                     'private': 'https://fapi.binance.com/fapi/v1',},}
 })

doneYet = []
ftx     = ccxt.ftx({
            'enableRateLimit': True,
            'apiKey': ftxKEY,   
            'secret': ftxSECRET,
        })

fundingEarned = {}
fundingEarned['totalsincerun'] = 0	
while True:
	fundingEarned['binance'] = 0
	fundingEarned['totalthishour'] = 0		
	fundingEarned['ftx'] = 0		
	income = binance.fapiPrivateGetIncome({'incomeType': 'FUNDING_FEE'})
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


	fundingEarned['totalsincerun'] = fundingEarned['totalsincerun']  + fundingEarned['binance'] + fundingEarned['ftx']
	fundingEarned['totalthishour'] = fundingEarned['binance'] + fundingEarned['ftx']

	print('Here are funding earnings from recent memory. Stay turned as it shows you data just from this point on! (stay tuned for huorly updates!')
	print(fundingEarned)
	sleep(60 * 60)