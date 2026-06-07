<template>
  <div class="status-banner" :class="{ active: active }">
    <span>{{ active ? text : "空闲" }}</span>
  </div>
</template>

<!-- 状态横幅组件：显示当前操作状态（空闲/活跃） -->
<script setup>
defineProps({
  active: {             // 是否忙碌中
    type: Boolean,
    default: false
  },
  text: {               // 状态文本
    type: String,
    default: ""
  }
});
</script>
