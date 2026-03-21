const statusNode = document.getElementById("status");
const roomCodeNode = document.getElementById("roomCode");
const suggestBtnNode = document.getElementById("suggestBtn");
const snapshotNode = document.getElementById("snapshot");
const suggestionNode = document.getElementById("suggestion");
const evaluationNode = document.getElementById("evaluation");
const attemptsNode = document.getElementById("attempts");

function writeJson(node, value) {
  node.textContent = JSON.stringify(value, null, 2);
}

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.classList.toggle("error", isError);
}

async function requestSuggestion(roomCode) {
  const response = await fetch("/api/suggest", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ roomCode }),
  });
  const payload = await response.json();
  return { ok: response.ok, payload };
}

async function handleSuggest() {
  const roomCode = roomCodeNode.value.trim();
  if (!roomCode) {
    setStatus("请先输入房间号。", true);
    return;
  }

  suggestBtnNode.disabled = true;
  setStatus("正在读取快照并生成合法建议...");
  writeJson(snapshotNode, {});
  writeJson(suggestionNode, {});
  writeJson(evaluationNode, {});
  writeJson(attemptsNode, []);

  try {
    const { ok, payload } = await requestSuggestion(roomCode);
    if (!ok || !payload.success) {
      setStatus(payload.message || "建议生成失败。", true);
      if (payload.snapshot) {
        writeJson(snapshotNode, payload.snapshot);
      }
      if (payload.attempts) {
        writeJson(attemptsNode, payload.attempts);
      }
      return;
    }

    setStatus(
      `建议生成成功，已尝试 ${payload.attemptCount} 次，最终方案合法。`
    );
    writeJson(snapshotNode, payload.snapshot || {});
    writeJson(suggestionNode, payload.suggestion || {});
    writeJson(evaluationNode, payload.evaluation || {});
    writeJson(attemptsNode, payload.attempts || []);
  } catch (error) {
    setStatus("请求失败，请确认服务已启动。", true);
    console.error(error);
  } finally {
    suggestBtnNode.disabled = false;
  }
}

suggestBtnNode.addEventListener("click", handleSuggest);
roomCodeNode.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    handleSuggest();
  }
});
