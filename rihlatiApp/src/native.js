import { Capacitor } from '@capacitor/core';
import { App } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import { Keyboard } from '@capacitor/keyboard';

window.RihlatiNative={
  isNative:Capacitor.isNativePlatform(),
  openWeb:url=>Browser.open({url}),
  tap:()=>Capacitor.isNativePlatform()?Haptics.impact({style:ImpactStyle.Light}).catch(()=>{}):Promise.resolve()
};
if(Capacitor.isNativePlatform()){
  App.addListener('backButton',()=>window.dispatchEvent(new Event('rihlati-back')));
  App.addListener('appStateChange',({isActive})=>window.dispatchEvent(new Event(isActive?'rihlati-resume':'rihlati-pause')));
  Keyboard.addListener('keyboardWillShow',()=>document.body.classList.add('keyboard-open'));
  Keyboard.addListener('keyboardWillHide',()=>document.body.classList.remove('keyboard-open'));
}
