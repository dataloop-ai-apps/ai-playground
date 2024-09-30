<script setup lang="ts">
// This starter template is using Vue 3 <script setup> SFCs
// Check out https://vuejs.org/api/sfc-script-setup.html#script-setup
import Panel from "./components/Panel.vue";
import { DlEvent, DlFrameEvent } from "@dataloop-ai/jssdk";
import { onMounted, ref } from "vue";
import { NodeConfig, NodeDescriptor } from "./models/PipelineNode";

const component = ref<NodeDescriptor>(null);
const theme = ref("light");
const readonly = ref(false);
const addItemMetadata = ref(true);
const overrideItemMetadata = ref(false);
const appUrl = ref("");

onMounted(() => {
  try {
    window.dl.on(DlEvent.NODE_CONFIG, async (eventPayload: NodeDescriptor) => {
      try {
        if (!eventPayload.metadata.customNodeConfig) {
          eventPayload.metadata.customNodeConfig = NodeConfig.DefaultValues;
        }
        component.value = new NodeDescriptor(
          NodeDescriptor.fromJSON(eventPayload)
        );
        addItemMetadata.value =
          component.value?.metadata?.customNodeConfig?.itemMetadata ?? true;
        overrideItemMetadata.value =
          component.value?.metadata?.customNodeConfig?.overrideItemMetadata ??
          false;
        await window.dl.agent.sendEvent({
          name: DlFrameEvent.UPDATE_NODE_CONFIG,
          payload: component.value,
        });
      } catch (e) {
        throw new Error("Error creating NodeConfig from nodeConfig event", e);
      }
    });
    window.dl.on(DlEvent.READY, async () => {
      try {
        const settings = (await window.dl.settings.get()) as any;
        theme.value = settings.theme;
        readonly.value = settings.readonly === "view";
      } catch (e) {
        throw new Error("Error getting settings", e);
      }
      const pipeline = await window.dl.pipelines.get();
      // appUrl.value =
      //   getUrlBeforePipeline((pipeline as any).url) +
      //   "/apps/" +
      //   getModifiedUrl(window.location.href) +
      //   "/panels/gradio/?pipeline=" +
      //   pipeline.name;

      appUrl.value =
        window.location.href.replace("/gradconfig", "/gradio") +
        "?pipeline=" +
        pipeline.name;

      window.dl.on(DlEvent.THEME, (mode: string) => {
        theme.value = mode;
      });

      window.dl.on("pipelineReadonly", ({ mode }: { mode: string }) => {
        readonly.value = mode === "view";
        console.log("Readonly mode", mode);
      });
    });
  } catch (e) {
    console.error("Error initializing xFrameDriver", e);
  }
});

const getUrlBeforePipeline = (url: string): string => {
  // Split the URL at "/pipelines/"
  const pipelineIndex = url.indexOf("/pipelines/");
  if (pipelineIndex !== -1) {
    // Return everything before "/pipelines/"
    return url.substring(0, pipelineIndex);
  }
  // Return the original URL if "/pipelines/" is not found
  return url;
};

const getModifiedUrl = (url: string): string => {
  // Remove "https://"
  let modifiedUrl = url.replace("https://", "");

  // Find the index of the first "."
  const firstDotIndex = modifiedUrl.indexOf(".");

  if (firstDotIndex !== -1) {
    // Return everything before the first "."
    modifiedUrl = modifiedUrl.substring(0, firstDotIndex);
  }

  return modifiedUrl;
};
</script>

<template>
  <dl-theme-provider :is-dark="theme === 'dark'">
    <div class="full-screen">
      <Panel
        :appUrl="appUrl"
        :component="component"
        :readonly="readonly"
        :addItemMetadata="addItemMetadata"
        :overrideItemMetadata="overrideItemMetadata"
        @add-item-metadata="addItemMetadata = $event"
        @override-item-metadata="overrideItemMetadata = $event"
      />
    </div>
  </dl-theme-provider>
</template>

<style scoped></style>
