import requests
s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.104.com.tw/jobs/search/',
})
s.get('https://www.104.com.tw/jobs/search/', timeout=10)
r = s.get('https://www.104.com.tw/jobs/search/api/jobs', params={
    'keyword': 'Accountant', 'order': '15', 'asc': '0',
    'page': '1', 'mode': 's', 'ro': '0', 'jobsource': 'index_s',
    'keywordType': 'label', 'searchJobs': '1', 'pageSize': '3', 'past': '7',
}, timeout=15)
for j in r.json().get('data', [])[:3]:
    link = (j.get('link') or {}).get('job', '')
    print('jobNo=' + str(j.get('jobNo')) + ' | link=' + str(link))
