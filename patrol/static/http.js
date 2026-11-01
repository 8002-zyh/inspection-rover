(function (root) {
  'use strict';
  // The deadline includes response-body decoding, even without AbortController.
  async function request(path, options, timeout, kind) {
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var opts = Object.assign({credentials: 'same-origin', cache: 'no-store'}, options || {});
    if (controller) opts.signal = controller.signal;
    return new Promise(function (resolve, reject) {
      var settled = false;
      var timer = setTimeout(function () {
        if (settled) return;
        settled = true;
        if (controller) controller.abort();
        reject(new Error('请求超时，请检查热点连接后重试'));
      }, timeout || 4000);
      function finish(fn, value) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        fn(value);
      }
      Promise.resolve().then(function () { return fetch(path, opts); }).then(async function (response) {
        if (kind === 'blob' && response.ok) return response.blob();
        var data;
        try { data = await response.json(); }
        catch (e) { throw new Error('服务器响应异常（HTTP ' + response.status + '），请刷新重试'); }
        if (!response.ok) throw new Error(data.error || '请求失败（HTTP ' + response.status + '）');
        return data;
      }).then(function (data) { finish(resolve, data); }, function (err) { finish(reject, err); });
    });
  }
  root.PatrolHttp = {request: request};
  if (typeof module !== 'undefined' && module.exports) module.exports = root.PatrolHttp;
})(typeof globalThis !== 'undefined' ? globalThis : window);
