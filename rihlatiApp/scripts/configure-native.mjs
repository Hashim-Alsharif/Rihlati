/* Reproducible brand assets only. Never writes signing keys or enables HTTP. */
import { readFile, writeFile, copyFile, mkdir, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const icon=path.join(root,'assets/icon.png');
for(const [density,size] of Object.entries({mdpi:48,hdpi:72,xhdpi:96,xxhdpi:144,xxxhdpi:192})){
  const directory=path.join(root,'android/app/src/main/res','mipmap-'+density);await mkdir(directory,{recursive:true});
  for(const name of ['ic_launcher.png','ic_launcher_round.png'])await sharp(icon).resize(size).png().toFile(path.join(directory,name));
}
const resources=path.join(root,'android/app/src/main/res');
// Adaptive icon foreground is centered inside Android's safe zone.
const logo=await readFile(path.join(root,'../Rihlati/app/logo-rihlati.svg'));
const mark=await sharp(logo).resize(176).png().toBuffer();
await sharp({create:{width:432,height:432,channels:4,background:'#00000000'}}).composite([{input:mark,gravity:'center'}]).png().toFile(path.join(resources,'drawable','rihlati_foreground.png'));
for(const name of ['ic_launcher.xml','ic_launcher_round.xml'])await writeFile(path.join(resources,'mipmap-anydpi-v26',name),'<?xml version="1.0" encoding="utf-8"?><adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android"><background android:drawable="@color/rihlati_icon_background"/><foreground android:drawable="@drawable/rihlati_foreground"/></adaptive-icon>\n');
await writeFile(path.join(resources,'values','rihlati_brand.xml'),'<?xml version="1.0" encoding="utf-8"?><resources><color name="rihlati_icon_background">#091a39</color></resources>\n');
const iosAssets=path.join(root,'ios/App/App/Assets.xcassets/AppIcon.appiconset');
await copyFile(icon,path.join(iosAssets,'AppIcon-512@2x.png'));
// Replace every generated platform splash asset, preserving the logo geometry.
for(const entry of await readdir(resources,{withFileTypes:true})){
  if(!entry.isDirectory()||!entry.name.startsWith('drawable'))continue;
  const splash=path.join(resources,entry.name,'splash.png');
  let metadata;try{metadata=await sharp(splash).metadata();}catch{continue;}
  const size=Math.round(Math.min(metadata.width,metadata.height)*.28);
  await sharp({create:{width:metadata.width,height:metadata.height,channels:4,background:'#091a39'}})
    .composite([{input:await sharp(logo).resize(size).png().toBuffer(),gravity:'center'}]).png().toFile(splash+'.new.png');
  await copyFile(splash+'.new.png',splash);
  const {unlink}=await import('node:fs/promises');await unlink(splash+'.new.png');
}
const splashAssets=path.join(root,'ios/App/App/Assets.xcassets/Splash.imageset');
const splashPng=await sharp({create:{width:2732,height:2732,channels:4,background:'#091a39'}})
  .composite([{input:await sharp(logo).resize(480).png().toBuffer(),gravity:'center'}]).png().toBuffer();
for(const file of ['splash-2732x2732.png','splash-2732x2732-1.png','splash-2732x2732-2.png'])await writeFile(path.join(splashAssets,file),splashPng);
console.log('Rihlati icons and splash screens updated; original logo preserved.');
