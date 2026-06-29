// 下载所有应用YAML文件（动态日期，格式：应用名_dify_workflow_YYYYMMDD.yaml）
(() => {
  // 1. 获取动态日期（格式：YYYYMMDD，自动补0处理）
  const getDynamicDate = () => {
    const date = new Date();
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0'); // 月份0-11，补0为2位
    const day = String(date.getDate()).padStart(2, '0'); // 日期1-31，补0为2位
    return `${year}${month}${day}`;
  };

  // 2. 基础配置
  const token = localStorage.console_token || sessionStorage.console_token || window.console_token;
  const dynamicDate = getDynamicDate(); // 动态生成当前日期
  if (!token) return console.error('❌ 未找到console_token，请先登录');

  // 3. 第一步：获取所有应用列表
  fetch('/console/api/apps?page=1&limit=30&name=&is_created_by_me=false', {
    headers: { 'Authorization': `Bearer ${token}` },
    credentials: 'include' // 确保鉴权凭证携带
  })
  .then(res => res.ok ? res.json() : Promise.reject(`❌ 应用列表请求失败：${res.status}`))
  .then(appListRes => {
    const apps = appListRes.data || [];
    if (apps.length === 0) return Promise.reject('❌ 未获取到任何应用数据');
    
    console.log(`✅ 共获取到${apps.length}个应用，开始批量下载...`);
    // 4. 第二步：遍历所有应用，逐个下载YAML
    apps.forEach((app, index) => {
      fetch(`/console/api/apps/${app.id}/export?include_secret=false`, {
        headers: { 'Authorization': `Bearer ${token}` },
        credentials: 'include'
      })
      .then(res => res.ok ? res.json() : Promise.reject(`❌ 应用【${app.name}】导出失败：${res.status}`))
      .then(exportJson => {
        // 生成符合要求的文件名：应用名_dify_workflow_YYYYMMDD.yaml
        const safeAppName = app.name || `unknown-app-${app.id}`; // 避免空应用名
        const fileName = `${safeAppName}_dify_workflow_${dynamicDate}.yaml`;
        
        // 生成YAML文件并触发下载
        const yamlBlob = new Blob([exportJson.data], { type: 'text/yaml;charset=utf-8' });
        const downloadUrl = URL.createObjectURL(yamlBlob);
        const aTag = document.createElement('a');
        
        aTag.href = downloadUrl;
        aTag.download = fileName;
        document.body.appendChild(aTag);
        aTag.click(); // 模拟点击下载
        
        // 清理临时资源
        document.body.removeChild(aTag);
        URL.revokeObjectURL(downloadUrl);
        
        console.log(`✅ 已下载(${index + 1}/${apps.length})：${fileName}`);
      })
      .catch(err => console.error(`❌ 应用【${app.name || app.id}】处理失败：`, err));
    });
  })
  .catch(err => console.error('❌ 整体流程失败：', err));
})();
