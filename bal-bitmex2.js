
var btc = 0;
const ccxt = require('ccxt')
          
        

        client     = new ccxt.binance({

            "options":{"defaultMarket":"futures"},
            'urls': {'api': {
                                     'public': 'https://fapi.binance.com/fapi/v1',
                                     'private': 'https://fapi.binance.com/fapi/v1',},}
 })

var client2 = new ccxt.deribit(

            {"apiKey": "",
            "secret": ""
 })
//client.urls['api'] = client.urls['test']
var usd2 = 0
var IM = 0
var orders = []
var LEV = 0
var olength = 0
var LEV_LIM = parseFloat(process.env.limit)
var startTime = new Date().getTime()
var btcstart
var usdstart
var btc4start
var usd4start
var usds = []
var levs = []
var usd4s = []
var prices = []
var btc4s = []
var btcs = []
var btc2 = 0
var usd4 = 0
var btc4 = 0
var ids = []
var vol = 0
var line
var tradesArr = []
var first = true;
var m;
var lines = []
var fee = 0
var btcusd;
var positions = []

setInterval(async function(){

	ethusd = await client.fetchTicker('ETH/USDT')
	ethusd = ethusd['last']
	btcusd = await client.fetchTicker('BTC/USDT')
	////console.log(btcusd)
btcusd = btcusd['last']

	////console.log(btcusd)
prices.push([new Date().getTime(), btcusd])
ethbtc = btcusd/ethusd


 request.get("http://localhost:4444/position", async function(e,r,d){
position2 = JSON.parse(d)
positions = []
for (var fut in position2){
for (var pos in position2[fut]){
	positions.push(position2[fut][pos])
}


}
 request.get("http://localhost:4444/margin", async function(e,r,d){

mex = parseFloat(JSON.parse(d)[0]['marginBalance'])/ 100000000	
 LEV=parseFloat(JSON.parse(d)[0]['marginLeverage'])
  
   //btc3=     parseFloat(bal = bal2.info.result[ 'USDT' ] ['total'])

//////////console.log(account)

//btc3 = parseFloat(account2 [ 'info' ] ['totalMarginBalance'])
////////console.log(btc)
btc2 = mex
console.log(btc2)

request.get("http://localhost:4444/order", async function(e,r,d){
orders2 = JSON.parse(d)
olength = 0
orders = []
for (var fut in orders2){
for (var order in orders2[fut]){
	if (orders2[fut][order].ordStatus.toLowerCase() == 'new'){
		olength++
		orders.push(orders2[fut][order])
	}
}
}
console.log(orders)

btc4 = btc
usd4 = btc4 * btcusd
usd2 = btc2 * btcusd

       console.log('lev')
       console.log(LEV)	
       console.log(usd2)
//////console.log(btc2)
if (first)
{
	btc4start = btc2
	usd4start = usd2
btcstart = btc2
first = false;
usdstart = btcstart * btcusd
////console.log(btcstart)
}

if (btc2 != 0){
	levs.push( [new Date().getTime(), LEV / LEV_LIM * 100])

	usds.push( [new Date().getTime(), -1 * (1-(usd2 / usdstart)) * 100])

btcs.push( [new Date().getTime(), -1 * (1-(btc2 / btcstart)) * 100])
	usd4s.push( [new Date().getTime(), -1 * (1-(usd4 / usd4start)) * 100])

btc4s.push( [new Date().getTime(), -1 * (1-(btc4 / btc4start)) * 100])

topost = {'theurl': theurl, 'amounts': 0, 'fees': 0, 'startTime': startTime, 'apikey': process.env.ftxkey, 'usd': usd2, 'btc': btc2, 'btcstart': btcs[0][0], 'usdstart': usds[0][0], 'funding': true}
                
               request.post("http://jare.cloud:8080/subscribers", {json:topost}, function(e,r,d){
               	console.log(d)})
               	} 
//////////console.log(btc)
})
})
})
}, 5500)
var theurl = process.env.theurl


const express = require('express');
var cors = require('cors');
var app = express();
app.use(cors());
var request = require("request")
var bodyParser = require('body-parser')
app.use(bodyParser.json()); // to support JSON-encoded bodies
app.use(bodyParser.urlencoded({ // to support URL-encoded bodies
    extended: true
}));
app.set('view engine', 'ejs');
app.listen(process.env.PORT || 80, function() {});
subscribers = {}
setInterval(async function(){
subscribers = {}

}, 10 * 60 * 1000)
app.post('/subscribers', cors(), (req, res) => {
let apikey = req.body.apikey
let apikey2 = req.body.apikey2
let usdstrat = false
if (apikey2 != undefined){
if (apikey2.length < 2){
usdstrat = false
}
else {
usdstrat = true

}
}

let btcsub = req.body.btc
let btcstartsub = req.body.btcstart
let fees = parseFloat(req.body.fees) * btcusd
let amounts = parseFloat(req.body.amounts)
let usdsub = req.body.usd
let usdstartsub = req.body.usdstart
let startTime = req.body.startTime
if (subscribers[apikey] == undefined){
subscribers[apikey] = {'usdstrat': usdstrat, 'amounts': amounts, 'fees': fees, 'btc': btcsub, 'btcstart': btcstartsub, 'usd': usdsub, 'usdstart': usdstartsub, 'pnlbtc': [startTime, 0], 'pnlusd': [startTime,0]}
console.log(apikey)
}
else{
	subscribers[apikey].amounts = amounts
	subscribers[apikey].usdstrat = usdstrat
	subscribers[apikey].fees = fees
	subscribers[apikey].btc = btcsub
	subscribers[apikey].btcstart = btcstartsub
	subscribers[apikey].usd = usdsub
	subscribers[apikey].usdstart = usdstartsub

subscribers[apikey].pnlbtc.push({'pnl': [startTime, -1 * (1-(btcsub / btcstartsub)) * 100], 'usdstrat': usdstrat})
subscribers[apikey].pnlusd.push({'pnl': [ startTime,-1 * (1-(usdsub / usdstartsub)) * 100], 'usdstrat': usdstrat})
	}
	//console.log(subscribers)
	//console.log(apikey + ' recent pnl btc: ' + subscribers[apikey].pnlbtc[subscribers[apikey].pnlbtc.length-1])

	//console.log(apikey + ' recent pnl usd: ' + subscribers[apikey].pnlusd[subscribers[apikey].pnlusd.length-1])
	res.send('ok')

	})


app.get('/update', cors(), (req, res) => {
pnlbtcs ={}
pnlusds = {}
feebtcs = {}
amtusds = {}
bal = 0
	usd = 0
	btcstart2 = 0
	usdstart2 = 0
	btc3 = 0
	usd3 = 0
	for (var sub in subscribers){
		usd3+=parseFloat(subscribers[sub].usd)
		usdstart2=parseFloat(subscribers[sub].usdstart)
	}
	for (var sub in subscribers){
		btc3=parseFloat(subscribers[sub].btc) 
		btcstart2=parseFloat(subscribers[sub].btcstart)
	}
for (var apikey in subscribers){
pnlbtcs[apikey.substring(0, 2)] = subscribers[apikey].pnlbtc[subscribers[apikey].pnlbtc.length-1]
pnlusds[apikey.substring(0, 2)] = subscribers[apikey].pnlusd[subscribers[apikey].pnlusd.length-1]
amtusds[apikey.substring(0, 2)] = parseFloat(subscribers[apikey].amounts )
feebtcs[apikey.substring(0, 2)] = parseFloat(subscribers[apikey].fees )
}
    res.json({btc: [new Date().getTime(), -1 * (1-(btc2 / btcstart)) * 100], 
    	btcusd: [new Date().getTime(), btcusd], 
    	usd: [new Date().getTime(), -1 * (1-(usd2 / usdstart)) * 100],
    	lev: [new Date().getTime(), LEV / LEV_LIM * 100],
    	orders: orders,
    	positions:positions,
    	 qty: vol, line:line, fee:fee * btcusd,
        theurl: theurl,
        olength: olength,
        start: startTime,
        apikey: process.env.KEY.substring(0, 5),
    	 pnlbtcs: pnlbtcs, subscribers: subscribers, feebtcs: feebtcs, amtusds: amtusds,
    	 pnlusds: pnlusds,btcbal: btc2, usddiff: -1 * (1-(usd3/ usdstart2)) * 100,  btcdiff:-1 * (1-(btc3 / btcstart2)) * 100, btcstart2, usdstart:usdstart})


})

app.get('/', (req, res) => {
        res.render('indexFunding.ejs', {
            btc: btcs, lines:lines,
            usd: usds,
            orders: orders,
            levs: levs,
            btcusd: prices,
        theurl: theurl
        })

});
