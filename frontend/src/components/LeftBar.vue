<script setup>

</script>

<template>
  <aside class="side panel">
    <nav class="tabs">

      <button>Бригады</button>
    </nav>

    <div>
      <div v-for="i in 15" class="brigada">
        <div class="brigada-title"> Бригада {{i}}</div>
      </div>
    </div>

  </aside>

</template>

<style scoped>
.brigada {
  padding: 10px;
  border: 1px dotted gray;
  margin: 10px 0px;
}

</style>