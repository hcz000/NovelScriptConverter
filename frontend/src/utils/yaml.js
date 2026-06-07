/** YAML 序列化工具：纯 JavaScript 实现的轻量级 YAML 格式化器。 */

/** 将标量值（字符串/数字/布尔/null）格式化为 YAML 表示 */
function formatScalar(value) {
  if (typeof value === "string") {
    return JSON.stringify(value);
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return "null";
}

function isScalar(value) {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

function formatKey(key) {
  return /^[A-Za-z0-9_-]+$/.test(key) ? key : JSON.stringify(key);
}

function serializeValue(value, depth) {
  const indent = "  ".repeat(depth);

  if (isScalar(value)) {
    return formatScalar(value);
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "[]";
    }

    return value
      .map((item) => {
        if (isScalar(item)) {
          return `${indent}- ${formatScalar(item)}`;
        }

        const nested = serializeValue(item, depth + 1);
        const lines = nested.split("\n");
        const nestedIndent = "  ".repeat(depth + 1);
        const firstLine = lines[0].startsWith(nestedIndent)
          ? lines[0].slice(nestedIndent.length)
          : lines[0];
        const remainingLines = lines.slice(1).join("\n");
        return remainingLines
          ? `${indent}- ${firstLine}\n${remainingLines}`
          : `${indent}- ${firstLine}`;
      })
      .join("\n");
  }

  const entries = Object.entries(value);
  if (entries.length === 0) {
    return "{}";
  }

  return entries
    .map(([key, item]) => {
      if (isScalar(item)) {
        return `${indent}${formatKey(key)}: ${formatScalar(item)}`;
      }

      const nested = serializeValue(item, depth + 1);
      return `${indent}${formatKey(key)}:\n${nested}`;
    })
    .join("\n");
}

/** 将 JavaScript 对象序列化为 YAML 格式字符串 */
export function toYaml(value) {
  return serializeValue(value, 0);
}
