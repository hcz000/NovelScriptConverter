import { defineStore } from "pinia";

import {
  createProject,
  exportScript,
  generateScript,
  getChapters,
  getProject,
  getScript,
  getTask,
  getVersions,
  parseProject,
  rewriteScene,
  updateScene,
  uploadSource
} from "../api/project";

const ACTIVE_PROJECT_STORAGE_KEY = "novel2script.activeProjectId";

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function readStoredProjectId() {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(ACTIVE_PROJECT_STORAGE_KEY) || "";
}

function writeStoredProjectId(projectId) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(ACTIVE_PROJECT_STORAGE_KEY, projectId);
}

function removeStoredProjectId() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(ACTIVE_PROJECT_STORAGE_KEY);
}

function buildSceneList(script) {
  return (script?.scenes || []).map((scene) => ({
    scene_id: scene.scene_id,
    title: scene.title,
    purpose: scene.purpose,
    characters: scene.characters
  }));
}

function getErrorMessage(error, fallback) {
  return error?.message || fallback;
}

async function waitTask(taskId, attempts = 120, interval = 1000) {
  for (let index = 0; index < attempts; index += 1) {
    const taskResponse = await getTask(taskId);
    const task = taskResponse.data;
    if (task.status === "SUCCEEDED") {
      return task;
    }
    if (task.status === "FAILED") {
      throw new Error(task.error_message || "task failed");
    }
    await sleep(interval);
  }
  throw new Error("task polling timeout");
}

export const useProjectStore = defineStore("project", {
  state: () => ({
    projectId: readStoredProjectId(),
    project: null,
    chapters: [],
    scenes: [],
    selectedVersionId: "",
    selectedSceneId: "",
    selectedScene: null,
    script: null,
    versions: [],
    loading: false,
    message: "",
    exportResult: null
  }),
  getters: {
    hasProject(state) {
      return Boolean(state.projectId);
    },
    activeVersionId(state) {
      return state.selectedVersionId || state.project?.current_version_id || "";
    },
    activeVersion(state) {
      const versionId = state.selectedVersionId || state.project?.current_version_id;
      return state.versions.find((version) => version.version_id === versionId) || null;
    },
    isViewingCurrentVersion(state) {
      if (!state.project) {
        return false;
      }
      return !state.selectedVersionId || state.selectedVersionId === state.project.current_version_id;
    }
  },
  actions: {
    setActiveProject(projectId) {
      this.projectId = projectId;
      if (projectId) {
        writeStoredProjectId(projectId);
      } else {
        removeStoredProjectId();
      }
    },
    clearProjectState() {
      this.setActiveProject("");
      this.project = null;
      this.chapters = [];
      this.scenes = [];
      this.selectedVersionId = "";
      this.selectedSceneId = "";
      this.selectedScene = null;
      this.script = null;
      this.versions = [];
      this.exportResult = null;
    },
    async hydrateProject() {
      if (!this.projectId || this.project) {
        return;
      }
      this.loading = true;
      this.message = "正在加载项目";
      try {
        await this.refreshAll();
        this.message = "项目已恢复";
      } catch (error) {
        this.clearProjectState();
        this.message = error?.message ? `项目恢复失败：${error.message}` : "项目恢复失败";
      } finally {
        this.loading = false;
      }
    },
    async bootstrapProject(title, file) {
      this.loading = true;
      this.message = "正在创建项目";
      try {
        const projectResponse = await createProject({
          title,
          language: "zh-CN"
        });
        this.setActiveProject(projectResponse.data.project_id);
        this.selectedVersionId = "";
        this.selectedSceneId = "";
        this.selectedScene = null;
        this.exportResult = null;
        this.project = {
          project_id: projectResponse.data.project_id,
          title: projectResponse.data.title,
          status: projectResponse.data.status
        };

        this.message = "正在上传小说";
        await uploadSource(this.projectId, file);

        this.message = "正在解析章节";
        const parseResponse = await parseProject(this.projectId, {
          min_chapter_count: 3,
          split_mode: "auto"
        });
        await waitTask(parseResponse.data.task_id);

        this.message = "正在生成剧本";
        const generateResponse = await generateScript(this.projectId, {
          target_format: "yaml",
          scene_granularity: "standard",
          include_report: true
        });
        await waitTask(generateResponse.data.task_id);

        await this.refreshAll();
        this.message = "项目初始化完成";
      } catch (error) {
        this.message = `项目初始化失败：${getErrorMessage(error, "请检查输入文件")}`;
        throw error;
      } finally {
        this.loading = false;
      }
    },
    syncSelectedScene() {
      if (!this.selectedSceneId || !this.script) {
        this.selectedScene = null;
        return;
      }
      this.selectedScene =
        this.script.scenes?.find((scene) => scene.scene_id === this.selectedSceneId) || null;
    },
    async refreshAll() {
      if (!this.projectId) {
        return;
      }
      const [projectResponse, chaptersResponse, versionsResponse] = await Promise.all([
        getProject(this.projectId),
        getChapters(this.projectId),
        getVersions(this.projectId)
      ]);
      this.project = projectResponse.data;
      this.chapters = chaptersResponse.data.items;
      this.versions = versionsResponse.data.items;

      const hasSelectedVersion = this.selectedVersionId
        ? this.versions.some((version) => version.version_id === this.selectedVersionId)
        : false;
      const versionId = hasSelectedVersion ? this.selectedVersionId : this.project.current_version_id || "";

      this.selectedVersionId = versionId;

      if (!versionId) {
        this.script = null;
        this.scenes = [];
        this.selectedSceneId = "";
        this.selectedScene = null;
        return;
      }

      const scriptResponse = await getScript(this.projectId, versionId);
      this.script = scriptResponse.data;
      this.scenes = buildSceneList(this.script);

      if (
        this.scenes.length > 0 &&
        (!this.selectedSceneId || !this.scenes.some((scene) => scene.scene_id === this.selectedSceneId))
      ) {
        this.selectedSceneId = this.scenes[0].scene_id;
      }

      if (!this.scenes.length) {
        this.selectedSceneId = "";
      }

      this.syncSelectedScene();
    },
    async selectVersion(versionId) {
      if (!this.projectId) {
        return;
      }
      this.selectedVersionId = versionId;
      this.selectedSceneId = "";
      this.exportResult = null;
      await this.refreshAll();
    },
    async loadScene(sceneId) {
      if (!sceneId) {
        this.selectedSceneId = "";
        this.selectedScene = null;
        return;
      }
      this.selectedSceneId = sceneId;
      this.syncSelectedScene();
    },
    async saveScene(payload) {
      if (!this.projectId || !this.selectedSceneId || !this.isViewingCurrentVersion) {
        return;
      }
      this.loading = true;
      this.message = "正在保存场景";
      try {
        await updateScene(this.projectId, this.selectedSceneId, payload);
        await this.refreshAll();
        this.message = "场景已保存";
      } catch (error) {
        this.message = `保存失败：${getErrorMessage(error, "请检查场景内容")}`;
        throw error;
      } finally {
        this.loading = false;
      }
    },
    async runRewrite(instruction) {
      if (!this.projectId || !this.selectedSceneId) {
        return;
      }
      this.loading = true;
      this.message = "正在重写场景";
      try {
        const response = await rewriteScene(this.projectId, this.selectedSceneId, {
          instruction,
          preserve_core_event: true,
          create_new_version: true
        });
        const task = await waitTask(response.data.task_id);
        this.selectedVersionId = task.result?.current_version_id || "";
        await this.refreshAll();
        this.message = "场景重写完成";
      } catch (error) {
        this.message = `重写失败：${getErrorMessage(error, "请调整重写指令")}`;
        throw error;
      } finally {
        this.loading = false;
      }
    },
    async runExport(format = "yaml") {
      if (!this.projectId) {
        return;
      }
      this.loading = true;
      this.message = "正在导出";
      try {
        const response = await exportScript(this.projectId, {
          version_id: this.activeVersionId || undefined,
          format,
          include_report: true
        });
        const task = await waitTask(response.data.task_id);
        this.exportResult = task.result;
        this.message = "导出完成";
      } catch (error) {
        this.message = `导出失败：${getErrorMessage(error, "请稍后重试")}`;
        throw error;
      } finally {
        this.loading = false;
      }
    }
  }
});
