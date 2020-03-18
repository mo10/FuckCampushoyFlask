function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
function hide(element){
    element.className = "trans hide";
}
function show(element){
    element.className = "trans";
}
var xhttp = new XMLHttpRequest();
function getJson(url,callback) {
    xhttp.onreadystatechange = function() {
        if (this.readyState === 4 && this.status === 200) {
            callback(JSON.parse(this.responseText));
        }
    };
    xhttp.open("GET", url, true);
    xhttp.send();
}

function loadEmpty() {
    document.getElementById('qrcode').src = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
}
function getValidation(){
    getJson(GET_VALIDATION_API, async function (e) {
            if(e.status === 0){
                switch (e.data) {
                    case 1:
                        getValidation();
                        break;
                    case 2:
                    case 3:
                        loadEmpty();
                        document.getElementById('status').innerText="扫码成功，请确认登陆";
                        getValidation();
                        break;
                    case 4:
                        loadEmpty();
                        document.getElementById('status').innerText="登陆成功，已添加到任务列表";
                        await sleep(2000);
                        window.location = '/';
                        break;
                    case 5:
                        loadEmpty();
                        document.getElementById('status').innerText="二维码失效,请刷新";
                        break;
                }
            }
            if(e.status !== 0){
                document.getElementById('status').innerText=e.errMsg;
            }
        });
}
function loadQRCode(){
    xhttp.abort();
    document.getElementById('status').innerText="正在加载二维码...";
    getJson(GET_QRCODE_API,function (e) {
        if(e.status === 0){
            document.getElementById('qrcode').src = 'data:image/png;base64, '+ e.data;
            document.getElementById('status').innerText="请扫描二维码登陆";
            getValidation();
        }
        if(e.status !== 0){
            document.getElementById('status').innerText=e.errMsg;
        }
    });
}
function saveAddress(){
    xhttp.abort();
    var addr = document.getElementById('address').value;
    getJson(SET_ADDRESS_API+'?addr='+addr,function (e) {
        if(e.status === 0){
            hide(document.getElementById('set-addr'));
            show(document.getElementById('qrform'));
            document.getElementById('now-address').innerText = addr;
            loadQRCode();
        }
    })
}
function rewriteAddress() {
    xhttp.abort();
    hide(document.getElementById('qrform'));
    show(document.getElementById( 'set-addr'));
}

function delTask(idx) {
    if(confirm("确认删除任务?")){
        getJson(DEL_TASK_API+'?idx='+idx,function (e) {
            if(e.status === 0){
                window.location = '/';
            }
        });
    }
}