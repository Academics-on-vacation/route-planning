<template>
  <div class="shell">
    <div class="tmp">Шапка?</div>

    <main class="grid">
      <LeftBar></LeftBar>
      <div class="col-main">
        <Map></Map>
        <div class="tmp">
          Диаграммы Ганта
        </div>
      </div>
    </main>

  </div>
</template>
<script setup lang="ts">
import Map from "./components/Map.vue";
import LeftBar from "./components/LeftBar.vue";
</script>

<style scoped>
.shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 330px minmax(0, 1fr);
  gap: 8px;
  padding: 8px;
}
.col-main {
  display: grid;
  grid-template-rows: minmax(0, 1.55fr) minmax(0, 1fr);
  gap: 8px;
  min-height: 0;
}

.tmp {
  background: rgba(0, 255, 255, 0.2);
  border: 3px dashed #2a4893;
  padding: 10px;
  border-radius: 25px;
  display: flex;
  align-items: center;
  align-content: center;
  justify-content: center;
  font-size: larger;
}
</style>