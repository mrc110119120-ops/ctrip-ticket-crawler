@echo off
REM Replay the user's EXACT captured batchSearch request via the real curl binary.
REM NUL bytes (^@) in w-payload-source are substituted with '@' (curl -H cannot carry NUL).
C:\Windows\System32\curl.exe "https://flights.ctrip.com/international/search/api/search/batchSearch?v=0.014012161395707823" ^
  --compressed ^
  -X POST ^
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:154.0) Gecko/20100101 Firefox/154.0" ^
  -H "Accept: application/json" ^
  -H "Accept-Language: zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5" ^
  -H "Accept-Encoding: gzip, deflate, br, zstd" ^
  -H "Referer: https://flights.ctrip.com/online/list/oneway-ckg-yty?_=1&depdate=2026-09-01&cabin=y_s&adult=1" ^
  -H "cookieOrigin: https://flights.ctrip.com" ^
  -H "Content-Type: application/json;charset=utf-8" ^
  -H "x-ctx-fvpc: " ^
  -H "transactionID: 095d270548e24ac8bde27cb591808d37" ^
  -H "scope: d" ^
  -H "x-ctx-ubt-pageid: 10320673302" ^
  -H "x-ctx-ubt-pvid: 1" ^
  -H "x-ctx-ubt-sid: 1" ^
  -H "Sessionid: 1" ^
  -H "x-ctx-ubt-vid: 1787992484819.de5b8sAwWgRM" ^
  -H "sign: b6dc88453241608f4e7c44833a2c47dd" ^
  -H "Cache-Control: no-cache" ^
  -H "token: 1001-common-MO8w0lWpfRSlYfOyA7rLFekFW8zjtUvGtR9hWlXWn5YpdRFby7XJ15rfdvLOvzTyS7yncwz9J5GiBQYLXEHzipSj5hWMaY3UjT8jfBvo5wd1KfZR6wZYLOr4oKaqKmZR7kynsjgmyfFv1lv6OJ9nv8dJAFi0PjQDEFNWPgxOyapioYmOxQXIO7I5kxlUwcprdYmgJ1aE5UWLlRMzyAPj3py6nvtgvnTY9sEhojolET8jpNRlGv4UIaFy8sjg6JaFJGajPcygUYscKldvSPx4mEnqro1vbOEsOydYGZJgdYlSJoURnaWGmJ98RslwcNyT9wXBy1TeopENpJT5vNnJUSeb3Eocjt3JXdwN4eD8vZ8JsHj5fWfZeFTy8pw6AJzSw40E0hvmUwFXyHqvBLEDOJqmjm6Kdnv5Gj9Yt5v1HwmqEm7YG5i0aYfkwOlvnAyg4YnQwSzYakia5WHYS7EZnesSe95Y3fEOJ8pildWfYanxcZydkjHTv9OeQcYhniDSY05JQaWXvhYPSjATRG5xq9em3ETFjkoWH4KaUJPkYOYSzj5crgdYOmr8LKzLetZEMdWa4RkFRdPKcYTGWmAx9kE7oRHaycdWB6yg7echRUtWO1wTlyNgvmoe1SYnYkw3GRagwhFRX8yTZWODyTmeoTRUXWm4RdavZZxk8Ipo" ^
  -H "Rms-Token: " ^
  -H "w-payload-source: 1.0.9@102@!YrjSzAClGPtbO2FV+rjd9PG5KEOP9lTI9l4IKrkR+EydOEKp9PKIOSkbOrK2+ET5+rApbbbpOSkZ+rV/+rqS+rbpbEkbKtb5+rbSKrbn+EKpOrGIOrK/+Et/OtbpOSkZ+rVnOEkL+EAIQPNaO64RTLCZF2hmrtb=" ^
  -H "Origin: https://flights.ctrip.com" ^
  -H "Connection: keep-alive" ^
  -H "Cookie: UBT_VID=1787992484819.de5b8sAwWgRM; _bfa=1.1787992484819.de5b8sAwWgRM.1.1787995761948.1787995953673.1.16.10320673302; GUID=09031028315695358455; _ga=GA1.1.1492546777.1787992485; _ga_5DVRDQD429=GS2.1.s1787992485$o1$g1$t1787993411$j59$l0$h220749065; _ga_B77BES1Z8Z=GS2.1.s1787992485$o1$g1$t1787993411$j59$l0$h0; Session=SmartLinkCode=chatgpt&SmartLinkKeyWord=&SmartLinkQuary=_UTF.&SmartLinkHost=chatgpt.com&SmartLinkLanguage=zh; MKT_CKID=1787992485531.i9iu4.jd2v; _jzqco=|||||1787992485753.1569816012.1787992485535.1787992485535.1787993411436.1787992485535.1787993411436.0.0.0.2.2; _RGUID=faabc331-f4f2-427b-b20d-a85f9181cb2f; Hm_lvt_a8d6737197d542432f4ff4abc6e06384=1787992486; Hm_lpvt_a8d6737197d542432f4ff4abc6e06384=1787993412; HMACCOUNT=2C6D4A78AF04EB2B; MKT_Pagesource=PC; nfes_isSupportWebP=1; _gid=GA1.2.701096265.1787992495; Union=AllianceID=4902&SID=130727&OUID=&createtime=1787993411&Expires=1788598211387; FlightIntl=Search=[CKG|重庆(CKG)|4|CKG|480,YTY|扬州(YTY)|15|YTY|480,2026-09-01]; _RF1=183.228.190.102; _RSG=x9ayq7pmhgFliSWH.5gD8B; _RDG=2895eb76e40037285e227148e888660508" ^
  -H "Sec-Fetch-Dest: empty" ^
  -H "Sec-Fetch-Mode: cors" ^
  -H "Sec-Fetch-Site: same-origin" ^
  -H "Priority: u=4" ^
  -H "TE: trailers" ^
  --data-raw '{"adultCount":1,"childCount":0,"infantCount":0,"flightWay":"S","cabin":"Y_S","scope":"d","segmentNo":1,"transactionID":"095d270548e24ac8bde27cb591808d37","flightSegments":[{"departureCityCode":"CKG","arrivalCityCode":"YTY","departureCityName":"重庆","arrivalCityName":"扬州","departureDate":"2026-09-01","departureCountryId":1,"departureCountryName":"中国","departureCountryCode":"CN","departureProvinceId":4,"departureCityId":4,"arrivalCountryId":1,"arrivalCountryName":"中国","arrivalCountryCode":"CN","arrivalProvinceId":15,"arrivalCityId":15,"departureCityTimeZone":480,"arrivalCityTimeZone":480,"timeZone":480}],"directFlight":false,"extGlobalSwitches":{"useAllRecommendSwitch":true,"unfoldPriceListSwitch":true},"noRecommend":false,"extensionAttributes":{"LoggingSampling":false,"isFlightIntlNewUser":false}}' ^
  -o curl_out.txt -w "%%{http_code}"
echo.
echo "HTTP_CODE ABOVE"
