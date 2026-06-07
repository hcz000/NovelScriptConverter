/** 项目 API 接口封装：封装所有后端 REST API 调用函数。 */
import client from "./client";

/** 创建项目 */
export function createProject(payload) {
  return client.post("/projects", payload);
}

/** 列出项目 */
export function listProjects(includeArchived = false) {
  return client.get("/projects", {
    params: includeArchived ? { include_archived: true } : {}
  });
}

/** 归档项目 */
export function archiveProject(projectId) {
  return client.post(`/projects/${projectId}/archive`);
}

/** 取消归档 */
export function unarchiveProject(projectId) {
  return client.post(`/projects/${projectId}/unarchive`);
}

/** 删除项目 */
export function deleteProject(projectId) {
  return client.delete(`/projects/${projectId}`);
}

/** 上传小说源文件 */
export function uploadSource(projectId, file) {
  const formData = new FormData();
  formData.append("file", file);
  return client.post(`/projects/${projectId}/source`, formData, {
    headers: {
      "Content-Type": "multipart/form-data"
    }
  });
}

/** 启动章节解析（异步任务） */
export function parseProject(projectId, payload) {
  return client.post(`/projects/${projectId}/parse`, payload);
}

/** 启动剧本生成（异步任务） */
export function generateScript(projectId, payload) {
  return client.post(`/projects/${projectId}/generate`, payload);
}

/** 获取项目详情 */
export function getProject(projectId) {
  return client.get(`/projects/${projectId}`);
}

/** 获取项目章节列表 */
export function getChapters(projectId) {
  return client.get(`/projects/${projectId}/chapters`);
}

/** 获取剧本数据 */
export function getScript(projectId, versionId) {
  return client.get(`/projects/${projectId}/script`, {
    params: versionId ? { version_id: versionId } : {}
  });
}

/** 获取场景概要列表 */
export function getScenes(projectId) {
  return client.get(`/projects/${projectId}/scenes`);
}

/** 获取单个场景详情 */
export function getScene(projectId, sceneId) {
  return client.get(`/projects/${projectId}/scenes/${sceneId}`);
}

/** 编辑场景内容 */
export function updateScene(projectId, sceneId, payload) {
  return client.patch(`/projects/${projectId}/scenes/${sceneId}`, payload);
}

/** 启动场景重写（异步任务） */
export function rewriteScene(projectId, sceneId, payload) {
  return client.post(`/projects/${projectId}/scenes/${sceneId}/rewrite`, payload);
}

/** 获取版本列表 */
export function getVersions(projectId) {
  return client.get(`/projects/${projectId}/versions`);
}

/** 对比两个版本 */
export function compareVersions(projectId, baseVersionId, targetVersionId) {
  return client.get(`/projects/${projectId}/versions/compare`, {
    params: {
      base_version_id: baseVersionId,
      target_version_id: targetVersionId
    }
  });
}

/** 启动剧本导出（异步任务） */
export function exportScript(projectId, payload) {
  return client.post(`/projects/${projectId}/export`, payload);
}

/** 查询异步任务状态 */
export function getTask(taskId) {
  return client.get(`/tasks/${taskId}`);
}

/** 获取同步导出下载链接 */
export function getExportDownloadUrl(projectId, format = "yaml", includeReport = true) {
  const params = new URLSearchParams({ format, include_report: includeReport });
  return `${client.defaults.baseURL}/projects/${projectId}/export/download?${params}`;
}
