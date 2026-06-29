(() => {
  // =============== 新增：自动提取 API 前缀 ===============
  const getApiBase = () => {
    const entry = performance.getEntries().find(e => 
      e.name.includes('/console/api') || e.name.includes('/api')
    );
    if (entry) {
      const url = new URL(entry.name, location.origin);
      const path = url.pathname;
      if (path.includes('/console/api')) {
        return url.origin + '/console/api';
      } else if (path.includes('/api')) {
        return url.origin + '/api';
      }
    }
    // 默认回退（Dify 控制台通常用 /console/api）
    return location.origin + '/console/api';
  };

  // =============== 新增：从Cookie提取指定值（通用方法） ===============
  const getCookie = (name) => {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  };

  // =============== 新增：获取Token（新老方式兼容，适配实际Cookie） ===============
  const getAuthToken = () => {
    // 1. 优先从Cookie获取 csrf_token（实际存在的Cookie键）
    let csrfToken = getCookie('csrf_token');
    let cookieKey = 'csrf_token';
    
    // 2. 兼容回退：若没找到 csrf_token，再试 x-csrf-token
    if (!csrfToken) {
      csrfToken = getCookie('x-csrf-token');
      cookieKey = 'x-csrf-token';
    }

    // 3. 找到CSRF Token则返回
    if (csrfToken) {
      console.log(`✅ 从Cookie获取到${cookieKey}：${csrfToken.substring(0, 20)}...`); // 脱敏输出
      return {
        type: 'csrf',
        token: csrfToken,
        cookieKey: cookieKey // 记录实际读取的Cookie键
      };
    }

    // 4. 回退到原有方式获取console_token
    const consoleToken = localStorage.console_token || sessionStorage.console_token || window.console_token;
    if (consoleToken) {
      console.log('✅ 从存储获取到console_token：', consoleToken.substring(0, 20) + '...');
      return {
        type: 'jwt',
        token: consoleToken
      };
    }

    // 5. 所有方式都失败
    return null;
  };

  // 1. 动态加载JSZip库（提供多个备用源解决跨域问题）
  const loadJSZip = () => {
    return new Promise((resolve, reject) => {
      console.log('🔧 正在加载ZIP打包库...');
      
      // 备用CDN列表（按优先级排序）
      const jsZipSources = [
        'https://cdn.staticfile.org/jszip/3.10.1/jszip.min.js', // 阿里云静态资源CDN（国内节点，稳定性强）
        'https://static.cloud.tencent.com/ajax/libs/jszip/3.10.1/jszip.min.js', // 腾讯云静态资源CDN（国内节点，覆盖广）
        'https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js', // jsDelivr CDN（国际知名开源库CDN）
        'https://unpkg.com/jszip@3.10.1/dist/jszip.min.js', // unpkg CDN（专注于npm包分发的CDN）
        'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js' // Cloudflare CDN（cdnjs项目，开源库分发）
      ];
      
      let currentSourceIndex = 0;
      
      const tryLoadSource = () => {
        if (currentSourceIndex >= jsZipSources.length) {
          reject(new Error('所有ZIP库源都加载失败，请检查网络或手动引入JSZip'));
          return;
        }
        
        const script = document.createElement('script');
        const currentSource = jsZipSources[currentSourceIndex].trim(); // 修复多余空格
        console.log(`尝试从源 ${currentSourceIndex + 1}/${jsZipSources.length} 加载: ${currentSource}`);
        
        script.src = currentSource;
        script.onload = () => {
          if (window.JSZip) {
            console.log('✅ ZIP库加载成功');
            resolve(window.JSZip);
          } else {
            console.warn(`❌ 源 ${currentSourceIndex + 1} 加载但未找到JSZip对象，尝试下一个源...`);
            currentSourceIndex++;
            tryLoadSource();
          }
        };
        
        script.onerror = () => {
          console.warn(`❌ 源 ${currentSourceIndex + 1} 加载失败，尝试下一个源...`);
          currentSourceIndex++;
          tryLoadSource();
        };
        
        setTimeout(() => {
          if (!window.JSZip) {
            console.warn(`⏰ 源 ${currentSourceIndex + 1} 加载超时，尝试下一个源...`);
            script.remove();
            currentSourceIndex++;
            tryLoadSource();
          }
        }, 10000);
        
        document.head.appendChild(script);
      };
      
      tryLoadSource();
    });
  };

  // 2. 获取动态日期（格式：YYYYMMDD，自动补0）
  const getDynamicDate = () => {
    const date = new Date();
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}${month}${day}`;
  };

  // 3. 核心：获取应用YAML并打包成ZIP
  const fetchAppsAndZip = async (JSZip) => {
    // =============== 关键修改：使用动态 API 前缀 ===============
    const API_BASE = getApiBase();
    console.log('🌐 检测到 API 基础地址:', API_BASE);

    // 获取认证Token（新老方式兼容）
    const authInfo = getAuthToken();
    const dynamicDate = getDynamicDate();
    
    // 校验Token
    if (!authInfo) {
      const errorMsg = '❌ 未找到有效的认证Token！\n- 未检测到 csrf_token / x-csrf-token Cookie\n- 未检测到console_token（localStorage/sessionStorage/window）\n请前往GitHub反馈此问题：https://github.com/xxx/xxx/issues';
      console.error(errorMsg);
      alert(errorMsg); // 弹窗提示，提升用户感知
      return;
    }

    try {
      // 构建请求头（适配不同Token类型，遵循通用标准）
      const requestHeaders = {};
      if (authInfo.type === 'jwt') {
        // JWT Token：使用Bearer认证头
        requestHeaders['Authorization'] = `Bearer ${authInfo.token}`;
      } else if (authInfo.type === 'csrf') {
        // CSRF Token：使用通用标准请求头（后端99%兼容这两个）
        requestHeaders['X-CSRFToken'] = authInfo.token; // Django/Flask等框架默认认这个
        requestHeaders['X-CSRF-Token'] = authInfo.token; // 兼容部分自定义后端
        // 可选：添加实际Cookie键作为请求头，兜底兼容
        requestHeaders[authInfo.cookieKey] = authInfo.token;
      }

      // 3.1 获取应用列表（使用完整 URL）
      console.log('🔍 正在获取Dify应用列表...');
      const appRes = await fetch(`${API_BASE}/apps?page=1&limit=100&name=&is_created_by_me=false`, {
        method: 'GET', // 显式指定GET，避免默认OPTIONS预检问题
        headers: requestHeaders,
        credentials: 'include' // 强制携带Cookie，适配CSRF认证
      });
      if (!appRes.ok) throw new Error(`应用列表请求失败：${appRes.status} ${appRes.statusText}`);

      const appData = await appRes.json();
      const apps = appData.data || [];
      if (apps.length === 0) {
        console.error('❌ 未获取到任何应用数据');
        return;
      }
      console.log(`✅ 共获取到 ${apps.length} 个应用，开始下载YAML并打包...`);

      // 3.2 初始化ZIP，批量添加YAML文件
      const zip = new JSZip();

      const addToZipPromises = apps.map((app, index) => {
        return fetch(`${API_BASE}/apps/${app.id}/export?include_secret=false`, {
          method: 'GET',
          headers: requestHeaders,
          credentials: 'include'
        })
        .then(res => {
          if (!res.ok) throw new Error(`应用【${app.name || app.id}】导出失败：${res.status} ${res.statusText}`);
          return res.json();
        })
        .then(exportJson => {
          const safeAppName = (app.name || `unknown-app-${app.id}`).replace(/[<>:"/\\|?*]/g, '_'); // 清理非法文件名字符
          const yamlFileName = `${safeAppName}.yaml`;
          zip.file(yamlFileName, exportJson.data);
          console.log(`✅ 已添加到压缩包 (${index + 1}/${apps.length})：${yamlFileName}`);
          return true;
        })
        .catch(err => {
          console.error(`❌ 应用【${app.name || app.id}】处理失败：${err.message}`);
          return false;
        });
      });

      await Promise.all(addToZipPromises);
      console.log('\n⏳ 正在生成ZIP压缩包...');
      const zipBlob = await zip.generateAsync({
        type: 'blob',
        compression: 'STORE' // 不压缩，提升速度（YAML文本压缩率低）
      });

      const zipFileName = `dify_apps_yaml_${dynamicDate}.zip`;
      const downloadUrl = URL.createObjectURL(zipBlob);
      const aTag = document.createElement('a');
      aTag.href = downloadUrl;
      aTag.download = zipFileName;
      document.body.appendChild(aTag);
      aTag.click();

      // 清理资源
      document.body.removeChild(aTag);
      URL.revokeObjectURL(downloadUrl);
      console.log(`\n🎉 压缩包生成完成！已下载：${zipFileName}`);
      console.log(`📌 提示：解压后可直接获取每个应用的独立YAML文件`);

    } catch (globalErr) {
      console.error(`\n❌ 整体流程失败：${globalErr.message}`);
      alert(`操作失败：${globalErr.message}\n请检查控制台日志或前往GitHub反馈`);
    }
  };

  // 启动流程
  loadJSZip()
    .then(JSZip => fetchAppsAndZip(JSZip))
    .catch(err => {
      console.error(`❌ 初始化失败：${err.message}`);
      alert(`初始化失败：${err.message}\n请检查网络或前往GitHub反馈此问题：https://github.com/AuditAIH/dify-workflow-batch-export/issues`);
    });
})();
