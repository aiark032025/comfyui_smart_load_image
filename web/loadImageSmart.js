import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Must match the sentinels in common.py
const ROOT_LABEL = "(root)";
const NONE_LABEL = "(no images)";

const NODE_NAME = "LoadImageSmart";

function getWidget(node, name) {
  return node.widgets ? node.widgets.find((w) => w.name === name) : undefined;
}

// Build an annotated image value "[subfolder/]filename [base]". This is the
// authoritative selection format (matches ComfyUI's mask editor contract).
function makeAnnotated(base, subfolder, filename) {
  const sub = subfolder && subfolder !== ROOT_LABEL ? subfolder + "/" : "";
  return `${sub}${filename} [${base}]`;
}

// Parse an annotated image value into {type, subfolder, filename}.
function parseAnnotated(value) {
  if (!value || value === NONE_LABEL) return null;
  let rest = value;
  let type = null;
  if (rest.endsWith("]")) {
    const idx = rest.lastIndexOf(" [");
    if (idx !== -1) {
      type = rest.slice(idx + 2, -1);
      rest = rest.slice(0, idx);
    }
  }
  rest = rest.replace(/\\/g, "/");
  let subfolder = "";
  let filename = rest;
  const slash = rest.lastIndexOf("/");
  if (slash !== -1) {
    subfolder = rest.slice(0, slash);
    filename = rest.slice(slash + 1);
  }
  return { type: type || "input", subfolder, filename };
}

async function listSubfolders(base) {
  try {
    const resp = await api.fetchApi(
      `/smartload/subfolders?base=${encodeURIComponent(base)}`
    );
    if (!resp.ok) return [];
    const data = await resp.json();
    return Array.isArray(data) ? data : [];
  } catch (e) {
    return [];
  }
}

async function listImages(base, subfolder) {
  const sub = subfolder === ROOT_LABEL ? "" : subfolder;
  try {
    const resp = await api.fetchApi(
      `/smartload/images?base=${encodeURIComponent(base)}&subfolder=${encodeURIComponent(sub)}`
    );
    if (!resp.ok) return [];
    const data = await resp.json();
    return Array.isArray(data) ? data : [];
  } catch (e) {
    return [];
  }
}

function updatePreview(node) {
  const imgW = getWidget(node, "image");
  if (!imgW) return;

  const ref = parseAnnotated(imgW.value);
  if (!ref) {
    node.imgs = null;
    node.setDirtyCanvas(true, true);
    return;
  }

  let url = `/view?filename=${encodeURIComponent(ref.filename)}&type=${encodeURIComponent(ref.type)}`;
  if (ref.subfolder) url += `&subfolder=${encodeURIComponent(ref.subfolder)}`;
  url += `&rand=${Math.random()}`;

  const img = new Image();
  img.onload = () => {
    node.imgs = [img];
    node.setDirtyCanvas(true, true);
  };
  img.onerror = () => {
    node.imgs = null;
    node.setDirtyCanvas(true, true);
  };
  try {
    img.src = api.apiURL(url);
  } catch (e) {
    /* ignore preview errors */
  }
}

/**
 * Re-fetch the subfolder + image lists and repopulate the combo options.
 *
 * The ``image`` widget value (annotated) is the authoritative selection. This
 * function NEVER discards a valid selection: when preserving, the current value
 * is kept as an option even if it lives outside the browsed folder (e.g. a mask
 * editor "clipspace/..." result). This is what avoids the reset-on-reload bug.
 *
 * @param {object} opts
 * @param {boolean} opts.keepSub        preserve current subfolder if still valid
 * @param {boolean} opts.keepImg        preserve current image if still valid
 * @param {string|null} opts.select     select this annotated value if present
 * @param {boolean} opts.syncFromImage  align browse selectors to the image value
 */
async function smartPopulate(node, opts = {}) {
  const {
    keepSub = true,
    keepImg = true,
    select = null,
    syncFromImage = false,
  } = opts;

  const baseW = getWidget(node, "base_folder");
  const subW = getWidget(node, "subfolder");
  const imgW = getWidget(node, "image");
  if (!baseW || !subW || !imgW) return;

  // Sequence token: a newer populate supersedes this one (avoids races between
  // load-time restore and user-driven changes).
  const seq = (node._smartSeq = (node._smartSeq || 0) + 1);

  // Optionally align the browse selectors with the authoritative image value.
  let desiredSub = null;
  if (syncFromImage) {
    const ref = parseAnnotated(imgW.value);
    if (ref) {
      const allowedBases = baseW.options?.values || [];
      if (allowedBases.includes(ref.type)) baseW.value = ref.type;
      desiredSub = ref.subfolder || "";
    }
  }

  const subs = await listSubfolders(baseW.value);
  if (seq !== node._smartSeq) return;

  let subValues = [ROOT_LABEL, ...subs];
  if (desiredSub !== null) {
    if (desiredSub === "") {
      subW.value = ROOT_LABEL;
    } else {
      if (!subValues.includes(desiredSub)) subValues = [...subValues, desiredSub];
      subW.value = desiredSub;
    }
  } else if (!(keepSub && subValues.includes(subW.value))) {
    subW.value = ROOT_LABEL;
  }
  subW.options.values = subValues;

  const subParam = subW.value === ROOT_LABEL ? "" : subW.value;
  const names = await listImages(baseW.value, subW.value);
  if (seq !== node._smartSeq) return;

  let imgValues = names.length
    ? names.map((n) => makeAnnotated(baseW.value, subParam, n))
    : [NONE_LABEL];

  const cur = imgW.value;
  if (keepImg && cur && cur !== NONE_LABEL && !imgValues.includes(cur)) {
    imgValues = [cur, ...imgValues];
  }
  imgW.options.values = imgValues;

  if (select && imgValues.includes(select)) {
    imgW.value = select;
  } else if (keepImg && imgValues.includes(cur)) {
    imgW.value = cur;
  } else {
    imgW.value = imgValues[0];
  }

  updatePreview(node);
  node.setDirtyCanvas(true, true);
}

function makeUploadInput(node) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.style.display = "none";

  input.onchange = async () => {
    if (!input.files || !input.files.length) return;
    const baseW = getWidget(node, "base_folder");
    const subW = getWidget(node, "subfolder");
    if (!baseW || !subW) return;

    const file = input.files[0];
    const body = new FormData();
    body.append("image", file);
    body.append("type", baseW.value);
    const sub = subW.value === ROOT_LABEL ? "" : subW.value;
    if (sub) body.append("subfolder", sub);
    body.append("overwrite", "false");

    try {
      const resp = await api.fetchApi("/upload/image", { method: "POST", body });
      if (resp.ok) {
        const data = await resp.json();
        const selected = makeAnnotated(
          data.type || baseW.value,
          data.subfolder || sub,
          data.name
        );
        await smartPopulate(node, { keepSub: true, select: selected });
      } else {
        console.error("[LoadImageSmart] upload failed", resp.status);
      }
    } catch (e) {
      console.error("[LoadImageSmart] upload error", e);
    } finally {
      input.value = "";
    }
  };

  document.body.append(input);
  return input;
}

function setupNode(node) {
  const baseW = getWidget(node, "base_folder");
  const subW = getWidget(node, "subfolder");
  const imgW = getWidget(node, "image");
  if (!baseW || !subW || !imgW) return;

  // Changing the base folder resets the subfolder (to root) and image.
  baseW.callback = () => {
    smartPopulate(node, { keepSub: false, keepImg: false });
  };

  // Changing the subfolder resets the image selection within it.
  subW.callback = () => {
    smartPopulate(node, { keepSub: true, keepImg: false });
  };

  // Selecting an image updates the preview.
  imgW.callback = () => {
    updatePreview(node);
  };

  const uploadInput = makeUploadInput(node);

  const refreshBtn = node.addWidget("button", "Refresh", null, () => {
    smartPopulate(node, { keepSub: true, keepImg: true });
  });
  refreshBtn.serialize = false;

  const uploadBtn = node.addWidget(
    "button",
    "choose image to upload",
    null,
    () => uploadInput.click()
  );
  uploadBtn.serialize = false;

  // Populate once after creation. Deferred so that, when loading a workflow,
  // this runs after litegraph has restored widget values via configure(); we
  // then preserve those restored values and sync the browse selectors to them.
  setTimeout(() => smartPopulate(node, { syncFromImage: true }), 0);
}

app.registerExtension({
  name: "comfyui.smart_load_image",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
      setupNode(this);
      return r;
    };

    // Re-populate after a workflow is loaded into this node, preserving the
    // values restored from the saved workflow.
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
      setTimeout(() => smartPopulate(this, { syncFromImage: true }), 0);
      return r;
    };
  },
});
