<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Phase 2</p>
        <h2>剧本工作台</h2>
      </div>
      <StatusBanner :active="store.loading" :text="store.message" />
    </header>

    <div v-if="!store.hasProject" class="empty-state">
      <p>先在导入页创建项目，再进入工作台。</p>
    </div>

    <div v-else class="workspace-grid">
      <aside class="card panel">
        <div class="panel-header">
          <h3>场景列表</h3>
          <button class="ghost-button" @click="store.refreshAll">刷新</button>
        </div>
        <p v-if="store.activeVersion" class="muted-text">
          当前版本：{{ store.activeVersion.version_name }}
        </p>
        <ul class="scene-list">
          <li v-for="scene in store.scenes" :key="scene.scene_id">
            <button
              class="scene-item"
              :class="{ selected: store.selectedSceneId === scene.scene_id }"
              @click="selectScene(scene.scene_id)"
            >
              <strong>{{ scene.title }}</strong>
              <span>{{ scene.scene_id }}</span>
            </button>
          </li>
        </ul>
      </aside>

      <section class="card panel editor-panel">
        <div class="panel-header">
          <h3>场景编辑</h3>
          <button
            class="primary-button"
            :disabled="!store.selectedScene || !store.isViewingCurrentVersion"
            @click="saveScene"
          >
            保存场景
          </button>
        </div>
        <p v-if="!store.isViewingCurrentVersion" class="muted-text">
          当前正在查看历史版本。请切回最新版本后再编辑或重写。
        </p>

        <div v-if="store.selectedScene" class="editor-form">
          <label class="field">
            <span>标题</span>
            <input v-model="form.title" :disabled="!store.isViewingCurrentVersion" />
          </label>
          <label class="field">
            <span>场景行</span>
            <input v-model="form.slugline" :disabled="!store.isViewingCurrentVersion" />
          </label>
          <label class="field">
            <span>场景目标</span>
            <textarea v-model="form.purpose" rows="4" :disabled="!store.isViewingCurrentVersion" />
          </label>

          <section class="field">
            <div class="beats-header">
              <span>节拍列表</span>
              <button
                class="ghost-button"
                :disabled="!store.isViewingCurrentVersion"
                @click="addBeat"
              >
                新增节拍
              </button>
            </div>
            <div class="beat-list">
              <article v-for="(beat, index) in form.beats" :key="index" class="beat-card">
                <div class="beat-toolbar">
                  <strong>节拍 {{ index + 1 }}</strong>
                  <button
                    class="ghost-button danger-button"
                    :disabled="!store.isViewingCurrentVersion"
                    @click="removeBeat(index)"
                  >
                    删除
                  </button>
                </div>
                <label class="field inline-field">
                  <span>类型</span>
                  <select v-model="beat.type" :disabled="!store.isViewingCurrentVersion">
                    <option value="action">动作</option>
                    <option value="dialogue">对白</option>
                  </select>
                </label>
                <label v-if="beat.type === 'dialogue'" class="field inline-field">
                  <span>角色</span>
                  <input v-model="beat.character" :disabled="!store.isViewingCurrentVersion" />
                </label>
                <label class="field">
                  <span>内容</span>
                  <textarea v-model="beat.content" rows="3" :disabled="!store.isViewingCurrentVersion" />
                </label>
              </article>
            </div>
          </section>

          <label class="field">
            <span>重写指令</span>
            <textarea
              v-model="rewriteInstruction"
              rows="4"
              placeholder="增强冲突张力，压缩节奏"
              :disabled="!store.isViewingCurrentVersion"
            />
          </label>
          <button class="ghost-button" :disabled="!store.isViewingCurrentVersion" @click="handleRewrite">
            执行 AI 重写
          </button>
        </div>

        <div v-else class="empty-state">
          <p>选择一个场景开始编辑。</p>
        </div>
      </section>

      <aside class="card panel preview-panel">
        <div class="panel-header">
          <h3>剧本体检</h3>
          <button class="ghost-button" @click="store.runExport()">导出</button>
        </div>
        <div v-if="qualityReport" class="quality-panel">
          <div class="quality-score">
            <strong>{{ qualityReport.overall_score }}</strong>
            <span>
              综合评分
              <small>{{ qualitySourceLabel }}</small>
            </span>
          </div>
          <p class="quality-headline">{{ qualityReport.headline }}</p>

          <section>
            <h4>比赛展示亮点</h4>
            <ul class="compact-list">
              <li v-for="highlight in qualityReport.pitch_highlights" :key="highlight">
                {{ highlight }}
              </li>
            </ul>
          </section>

          <section>
            <h4>分项评分</h4>
            <div class="metric-list">
              <div v-for="metric in qualityReport.metrics" :key="metric.name" class="metric-row">
                <span>{{ metric.name }}</span>
                <strong>{{ metric.score }}</strong>
              </div>
            </div>
          </section>

          <section v-if="qualityReport.revision_priorities?.length">
            <h4>下一轮优化</h4>
            <ul class="compact-list">
              <li v-for="priority in qualityReport.revision_priorities" :key="priority">
                {{ priority }}
              </li>
            </ul>
          </section>
        </div>
        <div v-else class="empty-state">
          <p>生成剧本后显示质量体检。</p>
        </div>

        <div class="panel-header preview-header">
          <h3>YAML 预览</h3>
        </div>
        <pre class="code-block">{{ formattedScript }}</pre>
        <div v-if="store.exportResult" class="export-box">
          <p>导出完成</p>
          <a :href="store.exportResult.download_url" target="_blank" rel="noreferrer">
            {{ store.exportResult.file_name }}
          </a>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";

import StatusBanner from "../components/StatusBanner.vue";
import { useProjectStore } from "../stores/project";
import { toYaml } from "../utils/yaml";

const store = useProjectStore();
const rewriteInstruction = ref("");
const form = reactive({
  title: "",
  slugline: "",
  purpose: "",
  beats: []
});

function createEmptyBeat(type = "action") {
  return {
    type,
    character: "",
    content: ""
  };
}

const formattedScript = computed(() => {
  if (!store.script) {
    return "暂无剧本数据";
  }
  return toYaml(store.script);
});

const qualityReport = computed(() => store.script?.quality_report || null);
const qualitySourceLabel = computed(() =>
  qualityReport.value?.generated_by === "llm" ? "LLM 审稿" : "规则审稿"
);

watch(
  () => store.selectedScene,
  (scene) => {
    if (!scene) {
      form.title = "";
      form.slugline = "";
      form.purpose = "";
      form.beats = [];
      return;
    }

    form.title = scene.title || "";
    form.slugline = scene.slugline || "";
    form.purpose = scene.purpose || "";
    form.beats = (scene.beats || []).map((beat) => ({
      type: beat.type || "action",
      character: beat.character || "",
      content: beat.content || ""
    }));
  },
  {
    immediate: true
  }
);

async function selectScene(sceneId) {
  await store.loadScene(sceneId);
}

function addBeat() {
  form.beats.push(createEmptyBeat());
}

function removeBeat(index) {
  form.beats.splice(index, 1);
}

function normalizeBeats() {
  return form.beats.map((beat) => ({
    type: beat.type,
    ...(beat.type === "dialogue" ? { character: beat.character.trim() } : {}),
    content: beat.content.trim()
  }));
}

async function saveScene() {
  try {
    await store.saveScene({
      title: form.title,
      slugline: form.slugline,
      purpose: form.purpose,
      beats: normalizeBeats(),
      change_note: "前端工作台保存"
    });
  } catch (error) {
    window.alert(error.message || "保存失败");
  }
}

async function handleRewrite() {
  if (!rewriteInstruction.value.trim()) {
    window.alert("请输入重写指令");
    return;
  }
  try {
    await store.runRewrite(rewriteInstruction.value.trim());
    rewriteInstruction.value = "";
  } catch (error) {
    window.alert(error.message || "重写失败");
  }
}
</script>
