var btc = 0;
const ccxt = require('ccxt')
const fs = require('fs');
const filename = 'intermediaryvalues.json';
fs.closeSync(fs.openSync(filename, 'w'));
const fileContents = fs.readFileSync('keys.txt', 'utf8')
keydata = {}
try {
   keydata = JSON.parse(fileContents)
} catch(err) {
  console.error(err)
}
const {RestClient} = require('@pxtrn/bybit-api');

KEY     = keydata["deribit"]["key"]
SECRET  = keydata["deribit"]["secret"]
mexkey = keydata["bitmex"]['key']
mexsecret = keydata["bitmex"]['secret']
bitkey = keydata["bybit"]['key']
bitsecret = keydata["bybit"]['secret']

const client2 = new RestClient(bitkey, bitsecret, true);

var client = new ccxt.deribit(

    {
        "apiKey": KEY,
        "secret": SECRET
    })
var binance = new ccxt.binance()
//console.log(client)
    var mex = new ccxt.bitmex(

        {
            "apiKey": mexkey,
            "secret": mexsecret
        })

const WebSocket = require('ws');

var reconnectInterval = 1 * 1000 * 10;
var ws;
var ws2;

var connect2 = function(){


    ws = new WebSocket('wss://www.deribit.com/ws/api/v2/');


ws.on('open', function open() {
	console.log('websocket open...')
    request.get("https://www.deribit.com/api/v2/public/auth?client_id=" + KEY + "&client_secret=" + SECRET + "&grant_type=client_credentials", function(e, r, d) {
        console.log(process.env.KEY)
		console.log(process.env.SECRET)
		console.log(d)
		d = JSON.parse(d)
        token = (d.result.access_token)
        args = {
            "channels": ["user.portfolio.btc"],
            "access_token": token
        };
        action = "private/subscribe"
        obj = {
            "method": action,
            "params": args
        };

        ws.send(JSON.stringify(obj))

        args = {
            "channels": ["user.portfolio.eth"],
            "access_token": token

        };
        action = "private/subscribe"
        obj = {
            "method": action,
            "params": args
        };

        ws.send(JSON.stringify(obj));
		
		args = {
             "channels": [
				  "chart.trades.BTC-PERPETUAL.1"
				]

        };
        action = "public/subscribe"
        obj = {
            "method": action,
            "params": args
        };

        ws.send(JSON.stringify(obj));
    })
});
var lasttick = 0;
ws.on('message', async function incoming(data) {
	
	
    message = JSON.parse(data)
    if (message['params'] != undefined) {
        if (message['params']['channel'] == 'user.portfolio.btc') {
            btce = message['params']['data']['equity']
            bals['deribit']['BTC'] = btce
        } else if (message['params']['channel'] == 'user.portfolio.eth') {
            if (ethbtc != 0) {
                ethe = message['params']['data']['equity'] / ethbtc
                bals['deribit']['ETH'] = ethe
            }
        }
		else if (message['params']['channel'] == 'chart.trades.BTC-PERPETUAL.1'){
			
		if (lasttick == 0){
			lasttick = message['params']['data'].tick
		} 
		else if (message['params']['data'] != lasttick){
			lasttick = message['params']['data']
			btcvol = (message['params']['data'].volume)
		}
		}
    }
    btc = btce + ethe
    console.log('btc123 ' + (btc).toString())
    console.log('btc123 ' + (btcusd).toString())
    console.log('btc123 ' + (gogo).toString())
    
    //console.log(btc)
    //console.log(btcusd)


});
    ws.on('error', function() {
        console.log('socket error');
        setTimeout(connect2, reconnectInterval);
    });
    ws.on('close', function() {
        console.log('socket close');
        setTimeout(connect2, reconnectInterval);
    });
};
connect2();



btce = 0
ethe = 0

btce2 = 0
ethe2 = 0
ethbtc = 0
gogo = false
setTimeout(function(){
    gogo = true
}, 3000)





var theurl = process.env.theurl

/*
var client = new ccxt.deribit(

            {"apiKey": "VC4d7Pj1",
            "secret": "IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"
 })

var client2 = new ccxt.deribit(

            {"apiKey": "5HkSPCwo",
            "secret": "z5fHc3FFB_SrVmEK6z0Unc-CjtHVU9_5pNMCdbXw_K0"
 })
 */
//client.urls['api'] = client.urls['test']
var usd2 = 0
var upnls = []
var rpnls = []
var tpnls = []
var btcstart
var usdstart
var btc4start
var usd4start
var usds = []
var usd4s = []
var btc3 = 0
var prices = []
var btc4s = []
var btcs = []
var btcbals = []
var usdbals = []
var btcVols = []
var btcvol = 0
var ones = []
var fives = []
var volAvgs = []
var epsVals = []
var btc2 = 0
var usd4 = 0
var btc4 = 0
var ts = new Date().getTime()
var ids = []
var vol = 0
var line
var tradesArr = []
var first = true;
var m;
var lines = []
var fee = 0
var btcusd = 0
var upnl = 0;
var fees = []
var vols = []
var rpnl = 0;
var tss = []
var one = 0;
var five = 0
var volAvg = 0
var eps = 0

var tpnl = 0;
async function setInitial() {
    ethusd = await client.fetchTicker('ETH-PERPETUAL')
    ethusd = ethusd['last']
    binancebtc = await binance.fetchTicker('BTC/USDT')

    btcusd = binancebtc['last']
    //console.log(btcusd)
    //console.log(ethusd)
    ethbtc = btcusd / ethusd
}
let bals = {}
bals['bitmex'] = {}
bals['bybit'] = {}
bals['deribit'] = {}
setInitial()
setInterval(async function() {
	    	newbtc2 = 0
	 request.get("http://localhost:4444/margin", async function(e,r,d){
mex = parseFloat(JSON.parse(d)[0]['amount'])/ 100000000	 
	 bals['bitmex']['BTC']  = mex
newbtc2 += mex
client2.getWalletBalance({'coin': 'BTC'})
  .then(result => {
    bitbtc = (result.result.BTC.equity);
    bals['bybit']['BTC'] = bitbtc
    newbtc2 += bitbtc
  })
  .catch(err => {
    console.error(err);
  });
  client2.getWalletBalance({'coin': 'ETH'})
  .then(result => {
    biteth= parseFloat(result.result.ETH.equity);
           
    bals['bybit']['ETH'] = biteth / ethbtc
    newbtc2 += (biteth / ethbtc)
  })
  .catch(err => {
    console.error(err);
  });

  client.fetchBalance({'coin': 'BTC'})
  .then(result => {
    bitbtc = (result.result.BTC.equity);
    bals['deribit']['BTC'] = bitbtc
    newbtc2 += bitbtc
  })
  .catch(err => {
    console.error(err);
  });
  client.fetchBalance({'coin': 'ETH'})
  .then(result => {
    biteth= parseFloat(result.result.ETH.equity);
           
    bals['deribit']['ETH'] = biteth / ethbtc
    newbtc2 += (biteth / ethbtc)

  })
  .catch(err => {
    console.error(err);
  });
   setTimeout(function(){
    	btc2 = newbtc2
    	if (btcstart == undefined || usdstart == undefined){
    		btcstart = new Date().getTime()
    		usdstart = new Date().getTime()
    	}
    }, 400)
	console.log(bals)
	console.log(bals)
	console.log(bals)
	if (gogo == true){
        btc4 = btc
        btcusdlast = btcusd
        usd4 = btc4 * btcusd
        usd2 = btc2 * btcusd
}
        //console.log(btc2)
       })
    	 account = await client.fetchBalance()

    //////console.log(account)
    upnl = (account.info.result.session_upl)
    rpnl = account.info.result.session_rpl
    tpnl = account.info.result.total_pl
	
	
    btc = parseFloat(account [ 'info' ] ['result']['equity'])
    account         = await client.fetchBalance({'currency':'ETH'})
    ////console.log(btc)
    ////console.log(ethbtc)
    //btc += parseFloat(account [ 'info' ] ['result']['equity']) / ethbtc

    //console.log(btcusd)
    //console.log(ethusd)
    prices.push([new Date().getTime(), btcusd])
    ethbtc = btcusd / ethusd

    //////console.log(trades.length)

    //////console.log(account)
    account = await client.fetchBalance()
    //////console.log(account)
    upnl = (account.info.result.session_upl)
    rpnl = account.info.result.session_rpl
    tpnl = account.info.result.total_pl
	
	
    //btc = parseFloat(account [ 'info' ] ['result']['equity'])
    //account         = await client.fetchBalance({'currency':'ETH'})
    ////console.log(btc)
    ////console.log(ethbtc)
    //btc += parseFloat(account [ 'info' ] ['result']['equity']) / ethbtc
    //btc3 = 0
    if (process.env.KEY2 != "") {
        //account2         = await client2.fetchBalance()
        //////console.log(account)

        //btc3 = parseFloat(account2 [ 'info' ] ['result']['equity'])
        //account2         = await client2.fetchBalance({'currency':'ETH'})

        //btc3 += parseFloat(account2[ 'info' ] ['result']['equity']) / ethbtc
        ////console.log(btc)
    }
	console.log('btc, btc2, usd2')
	console.log(btc)
	console.log(btc2)
	console.log(usd2)
    if (btc != 0 && btc2 != 0) {
        ts = (new Date().getTime())
        if (usd2 != 0) {
			var tsthen = new Date().getTime()
			if (btcs.length != 0){
			tsthen = btcs[btcs.length-1][0]
			}
			console.log('btcs length')
			console.log(btcs.length)
			if (btcs.length == 0 || tsthen < new Date().getTime() - 1000){
            tss.push(ts)

            tpnls.push(tpnl)
            rpnls.push(rpnl)
            upnls.push(upnl)

            fees.push(fee)
			btcVols.push([new Date().getTime(), btcvol])
            usdbals.push([new Date().getTime(), usd2])
            btcbals.push([new Date().getTime(), btc2])
            vols.push(vol)
			ones.push([new Date().getTime(), one])
			fives.push([new Date().getTime(), five])
			volAvgs.push([new Date().getTime(), volAvg])
			epsVals.push([new Date().getTime(), eps])
		
            usds.push([new Date().getTime(), -1 * (1 - (usd2 / usdstart)) * 100])

            btcs.push([new Date().getTime(), -1 * (1 - (btc2 / btcstart)) * 100])
            usd4s.push([new Date().getTime(), -1 * (1 - (usd4 / usd4start)) * 100])

            btc4s.push([new Date().getTime(), -1 * (1 - (btc4 / btc4start)) * 100])
			}
			else{
				console.log('not enuff time past yet...')
			}
			
	       }
    }
    //////console.log(btc)
}, 5000)

const express = require('express');
var cors = require('cors');

var app = express();
app.use(cors());
var starttime = new Date().getTime()
var request = require("request")
var bodyParser = require('body-parser')
app.set('view engine', 'ejs');
app.listen(process.env.PORT || 80, function() {});
app.get('/update', cors(), (req, res) => {
    res.json({
    	start:usds[0][0],
		btcVol: [new Date().getTime(), btcvol],
        btcbal: [new Date().getTime(),btc2],
        usdbal: [new Date().getTime(),usd2],
        btc: [new Date().getTime(), -1 * (1 - (btc2 / btcstart)) * 100],
        btcusd: [new Date().getTime(), btcusd],
        usd: [new Date().getTime(), -1 * (1 - (usd2 / usdstart)) * 100],
        start: starttime,
		one: [new Date().getTime(),one],
		five: [new Date().getTime(),five],
		volAvg: [new Date().getTime(),volAvg],
		epsVal: [new Date().getTime(),eps],
        apikey: process.env.KEY,
        vol: vol,
        line: line,
        fee: fee * btcusd,
        rpnl: rpnl,
        upnl: upnl,
        tpnl: tpnl,
        ts: ts,
        theurl: theurl,
    })

})

app.get('/', (req, res) => {
    res.render('fundingTracker.ejs', {
        btc: btcs,
		btcVols: btcVols,
		ones: ones,
		fives: fives,
		volAvgs: volAvgs,
		epsVals: epsVals,
        btcbal: btcbals,
        usdbal: usdbals,
        btcBals: btcbals,
        usdBals: usdbals,
        lines: lines,
        usd: usds,
        rpnls: rpnls,
        upnls: upnls,
        vols: vols,
        fees: fees,
        tpnls: tpnls,
        theurl: theurl,
        tss: tss,
        btcusd: prices
    })

});