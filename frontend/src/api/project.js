import client from "./client";

export function createProject(payload) {
  return client.post("/projects", payload);
}

export function uploadSource(projectId, file) {
  const formData = new FormData();
  formData.append("file", file);
  return client.post(`/projects/${projectId}/source`, formData, {
    headers: {
      "Content-Type": "multipart/form-data"
    }
  });
}

export function parseProject(projectId, payload) {
  return client.post(`/projects/${projectId}/parse`, payload);
}

export function generateScript(projectId, payload) {
  return client.post(`/projects/${projectId}/generate`, payload);
}

export function getProject(projectId) {
  return client.get(`/projects/${projectId}`);
}

export function getChapters(projectId) {
  return client.get(`/projects/${projectId}/chapters`);
}

export function getScript(projectId, versionId) {
  return client.get(`/projects/${projectId}/script`, {
    params: versionId ? { version_id: versionId } : {}
  });
}

export function getScenes(projectId) {
  return client.get(`/projects/${projectId}/scenes`);
}

export function getScene(projectId, sceneId) {
  return client.get(`/projects/${projectId}/scenes/${sceneId}`);
}

export function updateScene(projectId, sceneId, payload) {
  return client.patch(`/projects/${projectId}/scenes/${sceneId}`, payload);
}

export function rewriteScene(projectId, sceneId, payload) {
  return client.post(`/projects/${projectId}/scenes/${sceneId}/rewrite`, payload);
}

export function getVersions(projectId) {
  return client.get(`/projects/${projectId}/versions`);
}

export function exportScript(projectId, payload) {
  return client.post(`/projects/${projectId}/export`, payload);
}

export function getTask(taskId) {
  return client.get(`/tasks/${taskId}`);
}
