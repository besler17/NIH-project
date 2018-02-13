import simplejson as json
import requests
import pandas as pd
import numpy as np
from flask import Flask, render_template, request, redirect
from bokeh.plotting import figure
from bokeh.resources import CDN
from bokeh.embed import file_html
from bokeh.embed import components
from bokeh.layouts import row
from bokeh.models import Title
from bokeh.models import NumeralTickFormatter
from bokeh.models.glyphs import HBar
from sklearn.model_selection import train_test_split
import sklearn.svm
from requests_futures.sessions import FuturesSession
import pickle

app = Flask(__name__)

def cat_ratio(cat):
    total=0
    for item in cat.items():
        total=total+item[1]
    slst=sorted(cat.items(), key=lambda x:x[1])
    catelst=[str(i[0]) for i in slst]
    percentlst=[float(i[1])/total for i in slst]
    return catelst, percentlst
    

def get_year_dic(name, org):
    iniurl='https://api.federalreporter.nih.gov/v1/Projects/search?'
    urlp2='query=piName:'
    urlp3=name
    urlp4='$orgName:'
    urlp5=org
    url=iniurl+urlp2+urlp3+urlp4+urlp5
    url2=url+'&offset=51'
    response=requests.get(url)
        
    if len(response.text)==0:
        amount=[]
        cat=[]
        gwordlst=[]
        return (amount, cat, gwordlst)
    
    js=json.loads(response.text)
    prolst=js['items']
    if js['totalCount']>50:
        response2=requests.get(url2)
        js2=json.loads(response2.text)
        prolst2=js2['items']
        for i in prolst2:
            prolst.append(i)            
    exclude=['Life', 'Work', 'Study', 'Research', 'Science', 'Nature', 'Role', 'Roles', 'Goals', 'Goal']
    keydict=dict()
    for i in prolst:
        if len(i['terms'])==0:
            continue
        else:
            templst=[k.strip() for k in i['terms'].split(';')]
            for q in templst:
                if q not in exclude:
                    keydict[q]=keydict.get(q, 0)+1
    gwordlst=list()
    fieldlst=sorted(keydict.items(), key=lambda x:x[1], reverse=True)
    if len(fieldlst)>50:
        fieldlst=fieldlst[:50]
    max_c=fieldlst[0][1]
    min_c=fieldlst[-1][1]
    for p in fieldlst:
        temp={'text': p[0], 'size': int(((p[1] - (min_c-1)) / (max_c-min_c) * 30) + 20)}
        gwordlst.append(temp)
    
    df=pd.DataFrame(prolst)
    df1=df[df['budgetStartDate'].notnull()]
    df2=df[df['budgetStartDate'].isnull()]
    amount=dict()
    cat=dict()
    for i, r in df1.iterrows():
        cate=r['projectNumber'][1:4]
        cat[cate]=cat.get(cate, 0)+r['totalCostAmount']
        ymin=int(r['budgetStartDate'][:4])
        ymax=int(r['budgetEndDate'][:4])
        ycount=len(range(ymin, ymax+1))
        ave=r['totalCostAmount']/ycount
        ylst=[str(i) for i in range(ymin, ymax+1) if i<2017]
        for k in ylst:
            amount[k]=amount.get(k, 0)+ave
    for i, r in df2.iterrows():
        ymin=int(r['projectStartDate'][:4])
        ymax=int(r['projectEndDate'][:4])
        ycount=len(range(ymin, ymax+1))
        ave=r['totalCostAmount']/ycount
        ylst=[str(i) for i in range(ymin, ymax+1) if i<2017]
        for k in ylst:
            amount[k]=amount.get(k, 0)+ave            
    return (amount, cat, gwordlst)
    
@app.route('/')
def first_page():
    return render_template('firstp.html')

    
@app.route('/', methods=['POST'])
def second_page():
    
    ifdf=pd.read_csv('IFcsv.csv', skiprows=2)
    col_if=['Full Journal Title', 'Journal Impact Factor']
    ifdf=ifdf[col_if]
    ifdf=ifdf.iloc[:12052]
    
    ifdic=dict()
    for i, r in ifdf.iterrows():
        ifdic[r['Full Journal Title'].lower()]=float(r['Journal Impact Factor'])
            
    name=request.form['name']
    org=request.form['organization']
    
    (amount, cat, gword) = get_year_dic(name, org)
    if len(amount)==0:
        return render_template('p3.html')
    
    ylst=[]
    amoulst=[]
    for y, amou in sorted(amount.items(), key=lambda x:x[0]):
        ylst.append(y)
        amoulst.append(amou)
    first_year=ylst[0]
    total_amount="{:,}".format(round(sum(amoulst), 2))
    TOOLS='pan,wheel_zoom,box_zoom,reset, save'
    test = figure(plot_width=650, plot_height=400, tools=TOOLS, title='Amount of NIH Funding Received', x_axis_label='Year', y_axis_label='Funding Amount($)')
    test.line(ylst,amoulst, line_width=3, legend='PI: %s'%name)
    test.title.text_font_size = '14pt'
    test.left[0].formatter.use_scientific = False
    test.yaxis.formatter=NumeralTickFormatter(format='0,0')

    xlist, ylist=cat_ratio(cat)
    toolset='pan,wheel_zoom,box_zoom,reset, save'
    test2 = figure(y_range=xlist, plot_width=650, plot_height=400, tools=toolset, title='Funding By Category', x_axis_label='Percentage', y_axis_label='Funding Category')
    test2.hbar(y=xlist, height=0.5, left=0, right=ylist, color='steelblue', legend='PI: %s'%name)
    test2.xaxis.formatter=NumeralTickFormatter(format='0%')
    test2.title.text_font_size = '14pt'
    test2.legend.location='bottom_right'
    p = row(test, test2)
    script, div = components(p)
    
    
    #dfml['cat_cost']=map(category, dfml['t_cost'])        
    
    
    pubinfo=dict()
    pubinfo[name]=dict()
    pubinfo[name]['selfcount2008']=0
    pubinfo[name]['hiscount']=0
    pubinfo[name]['totalcount2008']=0
    pubinfo[name]['cocount2008']=0
    pubinfo[name]['highIF']=0
    pubinfo[name]['revcount']=0
    pubinfo[name]['sumIF']=0
    pubinfo[name]['aveIF']=0
    pubinfo[name]['count5years']=0
    pubinfo[name]['publist']=dict()
    
    session = FuturesSession(max_workers=10)
    
    urlname='http://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term='+name+'[author]&retmode=json&retmax=100'
    responses=requests.get(urlname)
    pubinfo[name]['hiscount']=int(json.loads(responses.text)['esearchresult']['count'])
    idlst=json.loads(responses.text)['esearchresult']['idlist']
    addresslst=['https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id='+item+'&retmode=json' for item in idlst]
    bbb=[json.loads(session.get(t).result().text) for t in addresslst]
    ccc=[i for i in bbb if int(i['result'][i['result']['uids'][0]]['pubdate'][:4])>=2008]
    
    for pub in ccc:
        item=pub['result']['uids'][0]
        if (name.split()[1].strip(',').lower() not in pub['result'][item]['lastauthor'].lower()) and (name.split()[1].strip(',').lower() not in pub['result'][item]['sortfirstauthor'].lower()):
            pubinfo[name]['cocount2008']=pubinfo[name]['cocount2008']+1
            continue
        pubinfo[name]['publist'][item]=dict()
        try:
            pubinfo[name]['publist'][item]['fulljournalname']=pub['result'][item]['fulljournalname']
            tname=pub['result'][item]['fulljournalname'].lower()
            titlename=pub['result'][item]['title'].encode('utf-8')
            if '(' in tname:
                n=tname.index('(')
                tname=tname[:n].strip()
            if ':' in tname:
                n=tname.index(':')
                tname=tname[:n].strip()
            if '.' in tname:
                n=tname.index('.')
                tname=tname[:n].strip()
            if tname.startswith('the '):
                tname=tname.lstrip('the ')
            pubinfo[name]['publist'][item]['IF']=ifdic[tname]
            pubinfo[name]['publist'][item]['title']=titlename
            if pubinfo[name]['publist'][item]['IF']>pubinfo[name]['highIF']:
                pubinfo[name]['highIF']=pubinfo[name]['publist'][item]['IF']
            pubinfo[name]['sumIF']=pubinfo[name]['sumIF']+pubinfo[name]['publist'][item]['IF']
            pubinfo[name]['publist'][item]['date']=int(pub['result'][item]['pubdate'][:4])
            if pubinfo[name]['publist'][item]['date']>=2012:
                pubinfo[name]['count5years']=pubinfo[name]['count5years']+1
            if ('Review' in pub['result'][item]['pubtype']) or ('rev' in pub['result'][item]['source'].lower()):
                pubinfo[name]['publist'][item]['review']=1
                pubinfo[name]['revcount']=pubinfo[name]['revcount']+1
            else:
                pubinfo[name]['publist'][item]['review']=0
            pubinfo[name]['selfcount2008']=pubinfo[name]['selfcount2008']+1
        except:
            pass
    try:
        pubinfo[name]['aveIF']=(pubinfo[name]['sumIF'])/(pubinfo[name]['selfcount2008'])
    except:
        pass         
    
    aat=[i for i in pubinfo[name]['publist'].items() if 'IF' in i[1]]
    bbt=sorted(aat, key=lambda x:x[1]['IF'], reverse=True)
    if len(bbt)>=3:
        bbt[0][1]
        j1=str(bbt[0][1]['date'])+',  "'+str(bbt[0][1]['fulljournalname'])+'",  '+bbt[0][1]['title'].decode('utf-8')
        j2=str(bbt[1][1]['date'])+',  "'+str(bbt[1][1]['fulljournalname'])+'",  '+bbt[1][1]['title'].decode('utf-8')
        j3=str(bbt[2][1]['date'])+',  "'+str(bbt[2][1]['fulljournalname'])+'",  '+bbt[2][1]['title'].decode('utf-8')
        
    lst=[pubinfo[name]['count5years'], pubinfo[name]['highIF'], pubinfo[name]['revcount'], pubinfo[name]['selfcount2008'], pubinfo[name]['aveIF']]
    loaded_model = pickle.load(open('model.sav', 'rb'))
    rank=int(loaded_model.predict(np.array(lst).reshape(1, -1))[0])
    aveif=round(pubinfo[name]['aveIF'], 3)
    c5=pubinfo[name]['count5years']
    rev_c=pubinfo[name]['revcount']
    
    return render_template('p2.html', script=script, div=div, rank=rank, first_year=first_year, total_amount=total_amount, name=name, aveif=aveif, c5=c5, rev_c=rev_c, gword=gword, j1=j1, j2=j2, j3=j3)
if __name__ == '__main__':
    app.run()