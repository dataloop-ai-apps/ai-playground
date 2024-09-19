<script setup lang="ts">
import { v4 } from "uuid";
import { cloneDeep, debounce, sumBy } from "lodash";
import { watch, ref, defineProps, computed, toRef, onUpdated } from "vue-demi";
import {
  NodeConfig,
  ValidationDescriptor,
  NodeDescriptor,
} from "../models/PipelineNode";
import { toFloat } from "../models/utils";
import { DlFrameEvent } from "@dataloop-ai/jssdk";

const props = defineProps<{
  appUrl: string;
  component: NodeDescriptor;
  readonly: boolean;
  addItemMetadata: boolean;
  overrideItemMetadata: boolean;
}>();
const emit = defineEmits(["addItemMetadata", "overrideItemMetadata"]);

const component = toRef(props, "component");
const readonly = toRef(props, "readonly");
const MAX_GROUP_NUMBER = 5;
const MIN_GROUP_NUMBER = 2;
const MAX_DISTRIBUTION = 100;
let groupNameErrorMessage = "";

const nodeName = ref(NodeConfig.DefaultValues.name);
const metadataKeySpecialCharError = ref(false);
const addItemMetadata = computed({
  get: () => {
    return props.addItemMetadata;
  },
  set: (val) => {
    emit("addItemMetadata", val);
  },
});

const overrideItemMetadata = computed({
  get: () => {
    return props.overrideItemMetadata;
  },
  set: (val) => {
    emit("overrideItemMetadata", val);
  },
});

onUpdated(() => {
  window.dl.agent.sendEvent({
    name: "app:setHeight",
    payload: document.body.scrollHeight,
  });
});

/** Creates a new group if allowed */
const onClick = async () => {
  // Modify the URL by removing "-nodes" and replacing "panels/gradconfig/" with "panels/gradio/" and add parameter pipeline which is the pipeline name
  const modifiedUrl = props.appUrl.replace("-nodes", "");

  // Open the modified URL in a new tab
  window.open(modifiedUrl, "_blank");
};

/** Validation of the metadata key */
const validateMetadataKey = (val: string) => {
  if (typeof val !== "string") {
    return;
  }
  metadataKeySpecialCharError.value = new RegExp(/[^\w_\-\.]/g).test(val);
};

/** Whether the distribution is valid */
const isDistributionValid = computed(() => {
  return true;
});

const nodeNameErrorMessage = computed(() => {
  if (!nodeName.value.length) {
    return "Node name is required";
  }
  if (!nodeName.value.match(/^[a-zA-Z0-9_\- ]+$/)) {
    return "Node name can only contain letters, numbers, underscores, hyphens and spaces";
  }
});

const trimNodeName = () => {
  nodeName.value = nodeName.value.trim();
};

const errors = computed((): { message: string; suggestion: string }[] => {
  const e = [];
  if (!!nodeNameErrorMessage.value) {
    e.push({
      message: "Node name error",
      suggestion: "Please adjust the node name",
    });
  }

  return e;
});

const validation = computed((): ValidationDescriptor => {
  return {
    valid: errors.value.length === 0,
    errors: errors.value,
  };
});

/** Sends the updated node config to the platform */
const debouncedUpdate = debounce(async () => {
  const nodeConfig = new NodeConfig({
    name: nodeName.value.trim(),
    validation: validation.value,
  });
  try {
    component.value.metadata.customNodeConfig = nodeConfig;
    component.value.outputs = [
      {
        portId: component.value.outputs[0].portId ?? v4(),
        name: "item",
        type: "Item",
      },
    ];
    await window.dl.agent.sendEvent({
      name: DlFrameEvent.UPDATE_NODE_CONFIG,
      payload: component.value,
    });
  } catch (error) {
    console.error(`Failed to send event`, { error });
  }
}, 200);

watch([nodeName, validation], debouncedUpdate, {
  deep: true,
});

watch(component, () => {
  const nodeConfig = component.value?.metadata.customNodeConfig;
  nodeName.value = nodeConfig.name;
});
</script>

<template>
  <div id="panel">
    <dl-input
      dense
      style="width: 100%; padding-bottom: 20px"
      placeholder="Insert node name"
      :error="!!nodeNameErrorMessage"
      :error-message="nodeNameErrorMessage"
      v-model="nodeName"
      title="Node Name"
      required
      @blur="trimNodeName"
      :disabled="readonly"
    />

    <dl-button label="Open Gradio App" size="m" @click="onClick" />

    <dl-list-item bordered style="margin-top: 20px" height="5px" />
  </div>
</template>

<style>
#groups-distribution > .dl-list-item {
  align-items: start !important;
}

.container {
  display: flex;
  flex-direction: row;
}

.dl-item__section--main {
  flex: 1 1 100% !important;
}

.dl-list-item {
  gap: 5px;
}

.item {
  flex-shrink: 1 !important;
  width: 100% !important;
}
.item-2 {
  flex-shrink: 1.3 !important;
  width: 100% !important;
}
</style>
