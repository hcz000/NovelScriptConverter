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
          <div class="header-rewrite">
            <input
              v-model="rewriteInstruction"
              class="rewrite-input"
              placeholder="重写指令，如：增强冲突张力"
              :disabled="!store.isViewingCurrentVersion"
              @keyup.enter="handleRewrite"
            />
            <button class="ghost-button" :disabled="!store.isViewingCurrentVersion" @click="handleRewrite">
              AI 重写
            </button>
          </div>
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
          <p class="quality-headline">{{ generationLabel }}</p>
          <p v-if="llmFallbackReason" class="muted-text">{{ llmFallbackReason }}</p>
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

<!-- 剧本工作台页面：核心编辑界面，包含场景列表、编辑器、质量报告和 YAML 预览 -->
<script setup>
import { computed, reactive, ref, watch } from "vue";

import StatusBanner from "../components/StatusBanner.vue";
import { useProjectStore } from "../stores/project";
import { toYaml } from "../utils/yaml";

const store = useProjectStore();
const rewriteInstruction = ref("");       // 重写指令输入
const form = reactive({                   // 编辑表单（与当前选中场景同步）
  title: "",
  slugline: "",
  purpose: "",
  beats: []
});

/** 创建一个空节拍（默认类型为 action） */
function createEmptyBeat(type = "action") {
  return {
    type,
    character: "",
    content: ""
  };
}

/** 将剧本数据格式化为 YAML 字符串（用于预览） */
const formattedScript = computed(() => {
  if (!store.script) {
    return "暂无剧本数据";
  }
  return toYaml(readableScript.value);
});

/** 当前剧本的质量报告 */
const qualityReport = computed(() => store.script?.quality_report || null);
/** 质量报告的来源标签（LLM 审稿 或 规则审稿） */
const qualitySourceLabel = computed(() =>
  qualityReport.value?.generated_by === "llm" ? "LLM 审稿" : "规则审稿"
);
const generationSource = computed(() => store.script?.metadata?.generation_source || "unknown");
const generationLabel = computed(() =>
  generationSource.value === "llm" ? "生成：LLM 增强" : "生成：规则引擎"
);
const llmFallbackReason = computed(() => {
  const reason = store.script?.metadata?.llm_fallback_reason;
  return reason ? `LLM 未参与生成：${reason}` : "";
});
const readableScript = computed(() => {
  const script = store.script;
  if (!script) return {};
  const metadata = script.metadata || {};
  const sourceSummary = script.source_summary || {};
  return {
    title: script.project?.title,
    version: script.project?.version,
    created_at: script.project?.created_at,
    generation_source: metadata.generation_source || "unknown",
    llm_status: metadata.llm_status || null,
    llm_fallback_reason: metadata.llm_fallback_reason || null,
    premise: sourceSummary.premise,
    main_conflict: sourceSummary.main_conflict,
    main_characters: (sourceSummary.main_characters || []).map(
      (profile) => `${profile.name}（${profile.role}）`
    ),
    scene_count: script.scenes?.length || 0,
    scenes: (script.scenes || []).map((scene) => ({
      scene_id: scene.scene_id,
      title: scene.title,
      heading: scene.slugline,
      purpose: scene.purpose,
      characters: scene.characters || [],
      dramatic_notes: {
        objective: scene.dramatic_structure?.objective,
        obstacle: scene.dramatic_structure?.obstacle,
        turning_point: scene.dramatic_structure?.turning_point
      },
      beats: (scene.beats || []).map((beat) =>
        beat.type === "dialogue"
          ? `${beat.character || "未标明"}：${beat.content}`
          : `动作：${beat.content}`
      )
    })),
    quality_report: qualityReport.value
      ? {
          overall_score: qualityReport.value.overall_score,
          headline: qualityReport.value.headline,
          revision_priorities: qualityReport.value.revision_priorities || []
        }
      : null
  };
});

/** 监听选中场景变化，同步更新编辑表单数据 */
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

/** 选择场景并加载详情 */
async function selectScene(sceneId) {
  await store.loadScene(sceneId);
}

/** 在节拍列表中添加一个新节拍 */
function addBeat() {
  form.beats.push(createEmptyBeat());
}

/** 删除指定索引的节拍 */
function removeBeat(index) {
  form.beats.splice(index, 1);
}

/** 规范化节拍数据：去除空字符，对白类型保留 character 字段 */
function normalizeBeats() {
  return form.beats.map((beat) => ({
    type: beat.type,
    ...(beat.type === "dialogue" ? { character: beat.character.trim() } : {}),
    content: beat.content.trim()
  }));
}

/** 保存场景编辑内容 */
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

/** 执行 AI 重写 */
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
