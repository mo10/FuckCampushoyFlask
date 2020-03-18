import os.path
import time
import json
import base64
import atexit
import requests
import logging
import threading
from urllib.parse import urlparse, parse_qsl
from flask import Flask, session, request, render_template
from apscheduler.schedulers.background import BackgroundScheduler


# Requests 库SSL校验 用于Debug
VERIFY = True
# task与日志保存路径
tasks_file = './tasks.json'
log_file = './logs.json'
# 轮询间隔时间
timers = 30
# 此处需要抓取问卷submit提交数据，填入request header中的Cpdaily-Extension字段内容
cpdaily_extension = 'To Request Heaedr Cpdaily-Extension Value'

lock = threading.Lock()
app = Flask(__name__)
app.config['SESSION_TYPE'] = 'memcached'
app.config['SECRET_KEY'] = '123456'
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
time_format = '%Y-%m-%d %I:%M:%S %p'

tasks = {
    'idx': 0,
    'data': []
}

logs = []

# Load Tasks
if os.path.isfile(tasks_file):
    with open(tasks_file, 'r') as f:
        tasks = json.load(f)
# load logs
if os.path.isfile(log_file):
    with open(log_file, 'r') as f:
        logs = json.load(f)


def loge(idx, status):
    logs.append({
        'idx': idx,
        'status': status,
        'time': time.strftime(time_format),
    })
    with open(log_file, 'w') as fd:
        json.dump(logs, fd)


def save_tasks():
    with open(tasks_file, 'w') as fd:
        json.dump(tasks, fd)


def auto_post(task, fwid, wid):
    # 检查地址
    if len(task['address'].strip()) == 0:
        print("Unknow address")
        loge(task['idx'], '未填写地址')
        return
    try:
        # 请求问卷内容
        r = requests.post(
            'https://ustl.cpdaily.com/wec-counselor-collector-apps/stu/collector/getFormFields',
            json={
                'pageSize': 10,
                'pageNumber': 1,
                'formWid': fwid,
                'collectorWid': wid
            }, headers={
                'Cookie': task['cookie']
            }, timeout=5, verify=VERIFY)
        frj = r.json()
        if frj['code'] != '0':
            loge(task['idx'], '请求问卷失败')
            return
        # 填写
        for row in frj['datas']['rows']:
            if row['fieldType'] != 1:
                task['status'] = '存在未知问题格式'
                task['lastupd'] = time.strftime(time_format)
                save_tasks()
                return
            if row['title'].find('是否') == -1:
                task['status'] = '模棱两可的问题'
                task['lastupd'] = time.strftime(time_format)
                save_tasks()
                return
            row['value'] = "否"
        # 提交
        r = requests.post(
            'https://ustl.cpdaily.com/wec-counselor-collector-apps/stu/collector/submitForm',
            data=json.dumps({
                'formWid': fwid,
                'address': task['address'].strip(),
                'collectWid': wid,
                'schoolTaskWid': None,
                'form': frj['datas']['rows'],
            }, ensure_ascii=False).encode('utf-8'),
            headers={
                'Content-type': 'application/json; charset=utf-8',
                'Cookie': task['cookie'],
                'CpdailyStandAlone': '0',
                'extension': '1',
                'Cpdaily-Extension': cpdaily_extension
            }, timeout=5, verify=VERIFY)
        rj = r.json()
        if rj['code'] != '0':
            loge(task['idx'], '提交问卷失败,%s' % rj['message'])
            task['status'] = '提交问卷失败'
            task['lastupd'] = time.strftime(time_format)
            save_tasks()
            return
        task['status'] = '提交成功'
        task['lastupd'] = time.strftime(time_format)
        save_tasks()
    except requests.exceptions.Timeout:
        loge(task['idx'], '问卷请求或提交超时')
    except:
        loge(task['idx'], 'auto_post错误')


def auto_poll():
    global tasks
    global logs

    with lock:
        for task in tasks['data']:
            try:
                r = requests.post(
                    'https://ustl.cpdaily.com/wec-counselor-collector-apps/stu/collector/queryCollectorProcessingList',
                    json={
                        'pageSize': 6,
                        'pageNumber': 1
                    }, headers={
                        'Cookie': task['cookie']
                    }, timeout=5, verify=VERIFY)
                rj = r.json()
                task['lastupd'] = time.strftime(time_format)
                # 请求失败
                if rj['code'] != '0':
                    task['status'] = rj['message']
                    loge(task['idx'], rj['message'])
                    save_tasks()
                    continue
                save_tasks()
                # 是否存在数据
                if rj['datas']['totalSize'] <= 0:
                    continue
                for row in rj['datas']['rows']:
                    if row['isHandled'] == 0:
                        auto_post(task, row['formWid'], row['wid'])
            except requests.exceptions.Timeout:
                loge(task['idx'], '请求超时')
            except:
                loge(task['idx'], 'auto_poll错误')


scheduler = BackgroundScheduler()
scheduler.add_job(func=auto_poll, trigger="interval", seconds=timers)
scheduler.start()
# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())


@app.route('/')
def index():
    with lock:
        return render_template('index.html', tasks=tasks, logs=logs)


@app.route('/newTask')
def new_task():
    with lock:
        return render_template('newTask.html', tasks=tasks)


@app.route('/getCode')
def get_code():
    try:
        # 请求clientId
        r = requests.get('https://ustl.cpdaily.com/wec-counselor-stu-apps/stu/mobile/index.html#/forAppNotice',
                         timeout=5, verify=VERIFY)
        session['cookie'] = r.request.headers['Cookie']
        query = dict(parse_qsl(urlparse(r.url).query))
        session['jslogin'] = {
            'clientId': query['client_id'],
            'redirectUri': query['redirect_uri'],
            'scope': query['scope'],
            'responseType': query['response_type'],
            'state': query['state'],
            'supportFreeLogin': '',
        }
        # 请求二维码id
        r = requests.post('https://www.cpdaily.com/connect/qrcode/jsLogin', json=session['jslogin'],
                          headers={'Cookie': session['cookie']},
                          timeout=5, verify=VERIFY)
        rj = r.json()
        # 请求失败
        if rj['errCode'] != 0:
            return {
                'status': 1,
                'errMsg': '%d,%s' % (rj['errCode'], rj['errMsg'])
            }
        # 下载二维码图像
        r = requests.get('https://www.cpdaily.com/connect/qrcode/image/%s' % rj['data']['qrId'],
                         headers={'Cookie': session['cookie']},
                         timeout=5, verify=VERIFY)
        session['qrid'] = rj['data']['qrId']
        return {
            'status': 0,
            'data': base64.b64encode(r.content).decode('ascii')
        }
    except requests.exceptions.Timeout:
        return {
            'status': 1,
            'errMsg': '服务器请求二维码超时'
        }


@app.route('/validation')
def get_validation():
    global tasks
    try:
        if 'cookie' in session and 'qrid' in session and 'jslogin' in session and 'address' in session:
            r = requests.post('https://www.cpdaily.com/connect/qrcode/validation/%s' % session['qrid'],
                              json=session['jslogin'], headers={'Cookie': session['cookie']}, verify=VERIFY)
            rj = r.json()
            if rj['data']['status'] == 4:
                # 获取 MOD_AUTH_CAS
                r = requests.get(rj['data']['redirectUrl'], verify=VERIFY)
                with lock:
                    tasks['idx'] += 1
                    tasks['data'].append({
                        'cookie': r.request.headers['Cookie'],
                        'address': session['address'],
                        'lastupd': 'N/A',
                        'idx': tasks['idx'],
                        'status': '正常',
                    })
                session.pop('cookie', None)
                session.pop('qrid', None)
                session.pop('jslogin', None)
            return {
                'status': 0,
                'data': rj['data']['status']
            }
        else:
            return {
                'status': 1,
                'errMsg': '请刷新二维码'
            }
    except requests.exceptions.Timeout:
        return {
            'status': 1,
            'errMsg': '服务器异常'
        }


@app.route('/setAddress', methods=['GET'])
def set_address():
    session['address'] = request.args.get('addr')
    return {
        'status': 0
    }


@app.route('/delTask', methods=['GET'])
def del_task():
    task_idx = request.args.get('idx')
    with lock:
        for idx in range(len(tasks['data'])):
            if tasks['data'][idx]['idx'] == int(task_idx):
                del(tasks['data'][idx])
                save_tasks()
    return {
        'status': 0
    }


if __name__ == '__main__':
    # Flask
    app.run(host='0.0.0.0', port=7920)
