// Calcula stateAt (frontend/src/overlay/state.ts) para conferir com a versão Python.
// Uso: node --experimental-strip-types tools/overlay_state.mjs entrada.json
// entrada: {"timeline": {...}, "times": [..]}  -> imprime a lista de estados em JSON
import { readFileSync } from "node:fs";
import { stateAt } from "../frontend/src/overlay/state.ts";

const { timeline, times } = JSON.parse(readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(times.map((t) => stateAt(timeline, t))));
