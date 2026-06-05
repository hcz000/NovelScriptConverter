import { defineStore } from "pinia";

import {
  createProject,
  exportScript,
  generateScript,
  getChapters,
  getProject,
  getScene,
  getScenes,
  getScript,
  getTask,
  getVersions,
  parseProject,
  rewriteScene,
  updateScene,
  uploadSource
} from "../api/project";

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
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
    projectId: "",
    project: null,
    chapters: [],
    scenes: [],
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
    }
  },
  actions: {
    async bootstrapProject(title, file) {
      this.loading = true;
      this.message = "正在创建项目";
      try {
        const projectResponse = await createProject({
          title,
          language: "zh-CN"
        });
        this.projectId = projectResponse.data.project_id;
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
      } finally {
        this.loading = false;
      }
    },
    async refreshAll() {
      if (!this.projectId) {
        return;
      }
      const [projectResponse, chaptersResponse, scriptResponse, scenesResponse, versionsResponse] =
        await Promise.all([
          getProject(this.projectId),
          getChapters(this.projectId),
          getScript(this.projectId),
          getScenes(this.projectId),
          getVersions(this.projectId)
        ]);
      this.project = projectResponse.data;
      this.chapters = chaptersResponse.data.items;
      this.script = scriptResponse.data;
      this.scenes = scenesResponse.data.items;
      this.versions = versionsResponse.data.items;
      if (!this.selectedSceneId && this.scenes.length > 0) {
        this.selectedSceneId = this.scenes[0].scene_id;
        await this.loadScene(this.selectedSceneId);
      } else if (this.selectedSceneId) {
        await this.loadScene(this.selectedSceneId);
      }
    },
    async loadScene(sceneId) {
      if (!this.projectId || !sceneId) {
        return;
      }
      this.selectedSceneId = sceneId;
      const response = await getScene(this.projectId, sceneId);
      this.selectedScene = response.data;
    },
    async saveScene(payload) {
      if (!this.projectId || !this.selectedSceneId) {
        return;
      }
      this.loading = true;
      this.message = "正在保存场景";
      try {
        await updateScene(this.projectId, this.selectedSceneId, payload);
        await this.refreshAll();
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
        await waitTask(response.data.task_id);
        await this.refreshAll();
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
          format,
          include_report: true
        });
        const task = await waitTask(response.data.task_id);
        this.exportResult = task.result;
      } finally {
        this.loading = false;
      }
    }
  }
});
