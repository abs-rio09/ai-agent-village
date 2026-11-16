// Where things stand on the village map. Everything is computed from HOW MANY there are — no
// position is tied to a name — so the map works for an empty village, for the six standard
// Upazilas and for any number the Chairman adds later. Units are SVG user units (the viewBox).

export interface Point {
  x: number;
  y: number;
}

export interface RingLayout {
  width: number;
  height: number;
  /** The plaza in the middle (Central Administration stands on it). */
  centre: Point;
  /** One ground point per building, clockwise from the top. */
  slots: Point[];
  /** Decoration: gardens in the gaps between the buildings. */
  gardens: Point[];
}

/** Buildings around a central plaza: the village level. `portrait` = a phone-shaped map. */
export function ringLayout(count: number, portrait: boolean): RingLayout {
  const width = portrait ? 380 : 960;
  if (portrait && count > 8) {
    // A phone is too narrow for a ring of that many: the plaza moves to the top and the
    // buildings stand in two columns below it.
    const centre = { x: width / 2, y: 150 };
    const rows = Math.ceil(count / 2);
    const slots = Array.from({ length: count }, (_, index) => {
      const row = Math.floor(index / 2);
      const alone = index === count - 1 && count % 2 === 1; // a last building without a neighbour is centred
      return { x: alone ? width / 2 : width / 2 + (index % 2 === 0 ? -92 : 92), y: centre.y + 196 + row * 150 };
    });
    return { width, height: centre.y + 196 + (rows - 1) * 150 + 110, centre, slots, gardens: [{ x: 52, y: centre.y + 40 }, { x: width - 52, y: centre.y + 40 }] };
  }
  const crowded = count > 8; // too many for one ring: every other building moves to an inner ring
  // Below a building come its robots and its sign (about 90 units), above it its roof and flag.
  const height = portrait ? 704 : crowded ? 700 : 630;
  const centre = { x: width / 2, y: height / 2 - 8 };
  const rx = portrait ? 124 : 356;
  const ry = portrait ? 240 : crowded ? 232 : 198;
  const at = (angle: number, factor: number): Point => ({
    x: Math.round(centre.x + Math.cos(angle) * rx * factor),
    y: Math.round(centre.y + Math.sin(angle) * ry * factor),
  });
  const step = count > 0 ? (2 * Math.PI) / count : 0;
  const slots = Array.from({ length: count }, (_, index) => at(-Math.PI / 2 + index * step, crowded && index % 2 === 1 ? 0.6 : 1));
  // gardens: halfway between neighbours, a little further in; four of them when there is nothing yet
  const gaps = count === 0 ? 4 : Math.min(count, 8);
  const gapStep = (2 * Math.PI) / gaps;
  const offset = count === 0 ? Math.PI / 4 : -Math.PI / 2 + step / 2;
  const gardens = Array.from({ length: gaps }, (_, index) => at(offset + index * gapStep, count <= 2 ? 0.8 : 0.56));
  return { width, height, centre, slots, gardens };
}

export interface GridLayout {
  width: number;
  height: number;
  columns: number;
  rows: number;
  cell: { width: number; height: number };
  /** One ground point (bottom centre of its cell) per item, row by row. */
  slots: Point[];
}

/** How many columns `count` items get: a tidy block, never wider than the map. */
export function gridColumns(count: number, portrait: boolean): number {
  if (count <= 1) return 1;
  if (portrait) return 2;
  if (count <= 4) return count;
  if (count <= 6 || count === 9) return 3;
  if (count <= 8) return 4;
  return 5;
}

/** Items in rows: Unions of an Upazila, Wards of a Union, workspaces of an Office. */
export function gridLayout(count: number, portrait: boolean, cellHeight = 170, top = 64): GridLayout {
  const width = portrait ? 380 : 960;
  const columns = gridColumns(count, portrait);
  const rows = Math.max(1, Math.ceil(count / columns));
  const cellWidth = Math.min(portrait ? 180 : 230, (width - 40) / columns);
  const height = top + rows * cellHeight + 40;
  const slots: Point[] = [];
  for (let index = 0; index < count; index += 1) {
    const row = Math.floor(index / columns);
    const inRow = row === rows - 1 ? count - row * columns : columns; // an incomplete last row is centred
    const column = index - row * columns;
    slots.push({
      x: Math.round(width / 2 + (column - (inRow - 1) / 2) * cellWidth),
      y: Math.round(top + (row + 1) * cellHeight - 34),
    });
  }
  return { width, height, columns, rows, cell: { width: cellWidth, height: cellHeight }, slots };
}

/** Shorten a name for a sign; the full name stays in the accessible label. */
export function fitText(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, Math.max(1, max - 1)).trimEnd()}…`;
}
