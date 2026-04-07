const sharp = require('sharp');
const fs = require('fs');

async function gen() {
  // SSTR sun symbol - trimmed, transparent background
  const sun = await sharp('sun_only.png').trim().toBuffer({ resolveWithObject: true });
  console.log(`Sun: ${sun.info.width}x${sun.info.height}`);

  for (const size of [512, 192]) {
    const sunSize = Math.round(size * 0.7);
    const pad = Math.round((size - sunSize) / 2);
    const resized = await sharp(sun.data)
      .resize(sunSize, sunSize, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .toBuffer();

    // Dark blue gradient background via compositing two layers
    const bg = await sharp({
      create: { width: size, height: size, channels: 4, background: { r: 26, g: 26, b: 46, alpha: 255 } }
    }).png().toBuffer();

    // Add subtle radial glow behind sun
    const glowSize = Math.round(size * 0.8);
    const glowData = Buffer.alloc(glowSize * glowSize * 4);
    const cx = glowSize / 2, cy = glowSize / 2, maxR = glowSize / 2;
    for (let y = 0; y < glowSize; y++) {
      for (let x = 0; x < glowSize; x++) {
        const dx = x - cx, dy = y - cy;
        const dist = Math.sqrt(dx * dx + dy * dy) / maxR;
        const alpha = Math.max(0, Math.round(80 * (1 - dist * dist)));
        const idx = (y * glowSize + x) * 4;
        glowData[idx] = 255;     // R - warm orange glow
        glowData[idx + 1] = 145;
        glowData[idx + 2] = 0;
        glowData[idx + 3] = alpha;
      }
    }
    const glow = await sharp(glowData, { raw: { width: glowSize, height: glowSize, channels: 4 } })
      .png().toBuffer();
    const glowPad = Math.round((size - glowSize) / 2);

    const icon = await sharp(bg)
      .composite([
        { input: glow, left: glowPad, top: glowPad },
        { input: resized, left: pad, top: pad }
      ])
      .png().toBuffer();

    await sharp(icon).toFile(`www/icon-${size}.png`);
    console.log(`www/icon-${size}.png`);

    if (size === 512) {
      // Android mipmap icons
      const mipmaps = [
        { name: 'mipmap-mdpi', size: 48 },
        { name: 'mipmap-hdpi', size: 72 },
        { name: 'mipmap-xhdpi', size: 96 },
        { name: 'mipmap-xxhdpi', size: 144 },
        { name: 'mipmap-xxxhdpi', size: 192 },
      ];
      for (const m of mipmaps) {
        const dir = `android/app/src/main/res/${m.name}`;
        const r = await sharp(icon).resize(m.size, m.size).png().toBuffer();
        await sharp(r).toFile(`${dir}/ic_launcher.png`);
        await sharp(r).toFile(`${dir}/ic_launcher_round.png`);
        // Foreground for adaptive icon
        const fgSize = Math.round(m.size * 1.5);
        const fgPad = Math.round((fgSize - m.size) / 2);
        const fg = await sharp({
          create: { width: fgSize, height: fgSize, channels: 4, background: { r: 26, g: 26, b: 46, alpha: 255 } }
        }).composite([
          { input: r, left: fgPad, top: fgPad }
        ]).png().toBuffer();
        await sharp(fg).resize(fgSize, fgSize).toFile(`${dir}/ic_launcher_foreground.png`);
        console.log(`${m.name}: ${m.size}px`);
      }
    }
  }
}

gen().catch(e => console.error(e));
