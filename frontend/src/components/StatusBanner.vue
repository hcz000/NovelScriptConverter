<template>
  <div class="status-banner" :class="{ active: active }">
    <span>{{ active ? text : "空闲" }}</span>
  </div>
</template>

<script setup>
defineProps({
  active: {
    type: Boolean,
    default: false
  },
  text: {
    type: String,
    default: ""
  }
});
</script>
