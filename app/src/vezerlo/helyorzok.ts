// A modulok jegyzet-parancsai (TERV 5.3, C17), amelyek még nem készültek el: helyőrzők a ⌘P-ben és a jegyzet helyi
// menüjében. A tulajdonos chat **ugyanazzal az azonosítóval** regisztrálja a valódi parancsot (előbb leiratkoztatja a
// helyőrzőt: `helyorzokTelepit` leiratkozója), a menü a regiszterből olvas, így nem kell hozzá nyúlni.

export interface Helyorzo {
  id: string;
  nev: string;
  /** a chat, amelyik elkészíti */
  chat: string;
}

/** C22b óta üres: minden C17-es jegyzet-parancsnak van valódi tulajdonosa (a mechanizmus marad a későbbi moduloknak). */
export const HELYORZOK: readonly Helyorzo[] = [];

/** A jegyzet helyi menüjének Manifold-parancsai (sorrendben): a helyőrzők és a már elkészült modulok parancsai (C24b: a
  *  `matek.*` a `matek/index.ts`-é, C23b: a `kartya.ebbol` a `kartya/index.ts`-é, C26b: az `osszefoglalas.keszit` az `osszefoglalas/index.ts`-é, C22b: a `kviz.ebbol` a `kviz/index.ts`-é). A menü a regiszterből olvas, a nem regisztrált azonosító kimarad. */
export const JEGYZET_MENU_PARANCSOK: readonly string[] = ['kartya.ebbol', 'kviz.ebbol', 'matek.megoldas', 'matek.levezetes', 'osszefoglalas.keszit'];
