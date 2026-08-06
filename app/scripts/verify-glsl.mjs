/**
 * No backtick may appear inside a GLSL template literal in `shaders.ts`.
 *
 * **This exists because the same mistake was made twice in one session, and it is a
 * particularly bad kind of mistake.** The shader sources are JavaScript template literals, so a
 * backtick inside one closes the string early. What follows is that the remaining GLSL is parsed
 * as JavaScript, and the failure surfaces as thirty type errors on lines nobody edited —
 * "Cannot find name 'aTrust'", "Module declaration names may only use quoted strings" — which
 * points at the shader body rather than at the prose comment that actually broke it.
 *
 * The temptation is constant: every other comment in this codebase quotes identifiers in
 * backticks, so writing `uTrust` inside a GLSL comment is the house style being applied one file
 * too far. Inside these two templates, identifiers go in plain text.
 *
 * Cheap enough to run on every check: it reads one file and scans it once.
 *
 * Run with `npm run verify:glsl`. Exits non-zero on any backtick inside a template.
 */
import { readFileSync } from 'node:fs';

const FILE = 'src/lib/galaxy/shaders.ts';
const lines = readFileSync(FILE, 'utf8').split('\n');

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(52)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(52)} FAIL ${detail}`);
	}
};

// Openers are `= /* glsl */ \``; the closer is a line that is exactly a backtick and a
// semicolon, which is how every template in this file is written and how prettier keeps them.
const opens = lines.reduce((acc, l, i) => (l.includes('/* glsl */ `') ? [...acc, i] : acc), []);
const offenders = [];
const templates = [];
for (const start of opens) {
	const end = lines.findIndex((l, i) => i > start && l.trim() === '`;');
	if (end < 0) {
		offenders.push(`${start + 1}: template is never closed`);
		continue;
	}
	templates.push([start, end]);
	for (let i = start + 1; i < end; i++) {
		if (lines[i].includes('`')) offenders.push(`${i + 1}: ${lines[i].trim().slice(0, 72)}`);
	}
}

console.log(`GLSL templates in ${FILE}`);
ok('every template is found and closed', opens.length > 0 && templates.length === opens.length,
	`${templates.length} template(s)`);
ok(
	'no backtick inside any of them',
	offenders.length === 0,
	offenders.length ? `\n    ${offenders.join('\n    ')}` : `${templates.length} scanned`
);

console.log(failures ? `\n${failures} GLSL check(s) failed` : '\nall GLSL checks passed');
process.exit(failures ? 1 : 0);
