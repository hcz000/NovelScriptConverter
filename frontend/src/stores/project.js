/** Pinia 项目状态管理 (useProjectStore)：
 *  核心 store，管理当前项目、项目列表、场景、版本等数据，
 *  封装所有 API 调用逻辑，提供高级操作如一键初始化和状态恢复。 */
import { defineStore } from "pinia";

import {
  archiveProject,
  compareVersions,
  createProject,
  deleteProject,
  generateScript,
  getChapters,
  getExportDownloadUrl,
  getProject,
  getScript,
  getTask,
  getVersions,
  listProjects,
  parseProject,
  rewriteScene,
  unarchiveProject,
  updateScene,
  uploadSource
} from "../api/project";

/** LocalStorage 键名：持久化当前活跃项目 ID */
const ACTIVE_PROJECT_STORAGE_KEY = "novel2script.activeProjectId";

/** 延迟工具函数（用于任务轮询等待） */
function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

/** 从 LocalStorage 读取上次活跃的项目 ID */
function readStoredProjectId() {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(ACTIVE_PROJECT_STORAGE_KEY) || "";
}

/** 将活跃项目 ID 写入 LocalStorage */
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

/** 从剧本数据中提取场景摘要列表（用于左侧导航） */
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

const TASK_WAIT_OPTIONS = {
  PARSE_CHAPTERS: { attempts: 180, interval: 1000 },
  GENERATE_SCRIPT: { attempts: 1200, interval: 1000 },
  REWRITE_SCENE: { attempts: 600, interval: 1000 },
  EXPORT_FILE: { attempts: 300, interval: 1000 },
  default: { attempts: 300, interval: 1000 }
};

function getTaskWaitOptions(taskType) {
  return TASK_WAIT_OPTIONS[taskType] || TASK_WAIT_OPTIONS.default;
}

function formatTaskTimeoutMessage(task) {
  const taskTypeLabel = {
    PARSE_CHAPTERS: "章节解析",
    GENERATE_SCRIPT: "剧本生成",
    REWRITE_SCENE: "场景重写",
    EXPORT_FILE: "文件导出"
  }[task.task_type] || "任务";
  const progress = task.progress ?? 0;
  const stage = task.stage ? `，阶段：${task.stage}` : "";
  return `${taskTypeLabel}仍在运行（${progress}%${stage}），LLM 生成可能需要更久，请稍后刷新或重试。`;
}

/** 轮询等待异步任务完成；生成类任务会比普通任务等待更久 */
async function waitTask(taskId, options = {}) {
  let waitOptions = null;
  for (let index = 0; index < TASK_WAIT_OPTIONS.GENERATE_SCRIPT.attempts; index += 1) {
    const taskResponse = await getTask(taskId);
    const task = taskResponse.data;
    if (!waitOptions) {
      waitOptions = {
        ...getTaskWaitOptions(task.task_type),
        ...options
      };
    }
    if (task.status === "SUCCEEDED") {
      return task;
    }
    if (task.status === "FAILED") {
      throw new Error(task.error_message || "task failed");
    }
    if (index + 1 >= waitOptions.attempts) {
      throw new Error(formatTaskTimeoutMessage(task));
    }
    await sleep(waitOptions.interval);
  }
  throw new Error(`任务仍在运行：${taskId}`);
}

/** Pinia Store：管理所有项目相关的状态和操作 */
export const useProjectStore = defineStore("project", {
  state: () => ({
    projectId: readStoredProjectId(),
    projects: [],
    showArchivedProjects: false,
    project: null,
    chapters: [],
    scenes: [],
    selectedVersionId: "",
    selectedSceneId: "",
    selectedScene: null,
    script: null,
    versions: [],
    versionCompare: null,
    loading: false,
    message: "",
    exportResult: null
  }),
  getters: {
    hasProject(state) {
      return Boolean(state.project);
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
      this.versionCompare = null;
      this.exportResult = null;
    },
    async loadProjects(includeArchived = this.showArchivedProjects) {
      this.showArchivedProjects = includeArchived;
      const response = await listProjects(includeArchived);
      this.projects = response.data.items;
    },
    async switchProject(projectId) {
      this.setActiveProject(projectId);
      this.project = null;
      this.chapters = [];
      this.scenes = [];
      this.selectedVersionId = "";
      this.selectedSceneId = "";
      this.selectedScene = null;
      this.script = null;
      this.versions = [];
      this.versionCompare = null;
      this.exportResult = null;
      await this.refreshAll();
    },
    async unarchiveActiveProject(projectId) {
      const targetProjectId = projectId || this.projectId;
      if (!targetProjectId) return;
      this.loading = true;
      this.message = "正在恢复项目";
      try {
        await unarchiveProject(targetProjectId);
        await this.loadProjects(this.showArchivedProjects);
        this.message = "项目已恢复";
      } finally {
        this.loading = false;
      }
    },
    async archiveActiveProject(projectId) {
      const targetProjectId = projectId || this.projectId;
      if (!targetProjectId) {
        return;
      }
      this.loading = true;
      this.message = "正在归档项目";
      try {
        await archiveProject(targetProjectId);
        if (targetProjectId === this.projectId) {
          this.clearProjectState();
        }
        await this.loadProjects(this.showArchivedProjects);
        this.message = "项目已归档";
      } finally {
        this.loading = false;
      }
    },
    async deleteActiveProject(projectId) {
      const targetProjectId = projectId || this.projectId;
      if (!targetProjectId) {
        return;
      }
      this.loading = true;
      this.message = "正在删除项目";
      try {
        await deleteProject(targetProjectId);
        if (targetProjectId === this.projectId) {
          this.clearProjectState();
        }
        await this.loadProjects(this.showArchivedProjects);
        this.message = "项目已删除";
      } finally {
        this.loading = false;
      }
    },
    /** 页面刷新后恢复项目状态（从 LocalStorage 读取上次项目 ID 重新加载） */
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
        this.message = "项目不存在或已被清理，请重新导入小说";
      } finally {
        this.loading = false;
      }
    },
    /** 一键初始化流程：创建项目 → 上传文件 → 解析章节 → 生成剧本 */
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
        this.versionCompare = null;
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
        await this.loadProjects(this.showArchivedProjects);
        this.message = "项目初始化完成";
      } catch (error) {
        try {
          await this.refreshAll();
          await this.loadProjects(this.showArchivedProjects);
        } catch {
          // Keep the original error message.
        }
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
    /** 刷新全部项目数据：项目详情、章节、版本、剧本、场景 */
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
      this.versionCompare = null;
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
    /** 执行 AI 场景重写 */
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
    /** 执行剧本导出（直接触发浏览器下载，不写服务器磁盘） */
    async runExport(format = "yaml") {
      if (!this.projectId) {
        return;
      }
      const url = getExportDownloadUrl(this.projectId, format, true);
      this.exportResult = { download_url: url, file_name: `${this.project?.title || "script"}.${format}` };
      this.message = "导出完成";
      window.open(url, "_blank");
    },
    /** 对比两个版本之间的差异 */
    async compareVersionPair(baseVersionId, targetVersionId) {
      if (!this.projectId || !baseVersionId || !targetVersionId) {
        this.versionCompare = null;
        return;
      }
      this.loading = true;
      this.message = "正在对比版本";
      try {
        const response = await compareVersions(this.projectId, baseVersionId, targetVersionId);
        this.versionCompare = response.data;
        this.message = "版本对比完成";
      } catch (error) {
        this.message = `版本对比失败：${getErrorMessage(error, "请检查版本")}`;
        throw error;
      } finally {
        this.loading = false;
      }
    }
  }
});
