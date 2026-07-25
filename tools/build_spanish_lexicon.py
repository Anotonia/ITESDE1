#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "spanish-card-lexicon"
OUT.mkdir(parents=True, exist_ok=True)

FREQ_URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/es/es_50k.txt"
FREQ_PATH = OUT / "es_50k.txt"

# Manual teaching policy: auditable, deliberately conservative.
DENY_EXACT = {
    "mierda","puta","puto","culo","coño","joder","hostia","carajo","idiota","estúpido","estupido",
    "asesino","asesinato","matar","muerto","muerta","arma","armas","sexo","dólares","dolares",
    "john","jack","sam","york","michael","david","george","charlie","tom","mike","joe","frank",
    "madrid","españa","china","francia","alemania","italia","europa","américa","america",
}
DENY_PATTERNS = [
    re.compile(r"^[a-záéíóúüñ]\.$", re.I),
    re.compile(r"^[a-z]{1,2}$", re.I),
    re.compile(r"\d"),
    re.compile(r"[._/@+#]"),
]
ALLOWED_CHARS = re.compile(r"^[a-záéíóúüñ]+$", re.I)

# Function words retained only if length >=3 and pedagogically useful/common.
A1_FUNCTION = {
    "con","por","para","sin","pero","como","muy","más","mas","aquí","aqui","allí","alli","hoy",
    "ayer","ahora","antes","después","despues","donde","cuando","porque","sobre","entre","hasta",
    "desde","bien","mal","sí","si","no","uno","una","dos","tres","cuatro","cinco","seis","siete",
    "ocho","nueve","diez","este","esta","estos","estas","ese","esa","esos","esas","otro","otra",
}

A1_CORE = {
    "hola","gracias","adiós","adios","favor","casa","familia","madre","padre","hijo","hija","hermano",
    "hermana","amigo","amiga","niño","niña","niños","niñas","hombre","mujer","persona","gente","nombre",
    "día","dia","noche","mañana","manana","tarde","hora","tiempo","semana","mes","año","ano","hoy",
    "agua","café","cafe","comida","pan","vino","leche","carne","pescado","fruta","mesa","cama","silla",
    "puerta","ventana","baño","bano","cocina","calle","ciudad","pueblo","escuela","clase","libro","carta",
    "coche","auto","tren","barco","avión","avion","viaje","hotel","tienda","ropa","foto","música","musica",
    "sol","luz","aire","tierra","mar","cielo","fuego","mano","cabeza","cara","ojo","ojos","boca","pie",
    "perro","gato","casa","trabajo","dinero","mundo","vida","amor","idea","problema","pregunta","respuesta",
    "bueno","buena","malo","mala","grande","pequeño","pequeno","pequeña","pequena","nuevo","nueva","viejo",
    "vieja","bonito","bonita","fácil","facil","difícil","dificil","rápido","rapido","lento","feliz","triste",
    "caliente","frío","frio","alto","bajo","blanco","negro","rojo","verde","azul","uno","dos","tres",
    "ser","estar","tener","hacer","ir","venir","ver","mirar","hablar","decir","comer","beber","vivir",
    "trabajar","estudiar","leer","escribir","comprar","pagar","abrir","cerrar","entrar","salir","dormir",
    "jugar","gustar","querer","poder","saber","conocer","llamar","llevar","tomar","dar","poner","buscar",
    "encontrar","esperar","ayudar","necesitar","pensar","creer","volver","pasar","usar","caminar","correr",
}

# Common concrete A2 domains, still conservative.
A2_CORE = A1_CORE | {
    "oficina","empresa","negocio","reunión","reunion","equipo","servicio","información","informacion","mensaje",
    "teléfono","telefono","programa","sistema","control","situación","situacion","decisión","decision","derecho",
    "oportunidad","seguridad","accidente","hospital","médico","medico","doctor","policía","policia","gobierno",
    "universidad","profesor","película","pelicula","fiesta","cumpleaños","cumpleanos","boda","vacaciones",
    "aeropuerto","estación","estacion","dirección","direccion","camino","centro","campo","playa","montaña",
    "montana","río","rio","bosque","animal","pájaro","pajaro","caballo","vaca","árbol","arbol","flor",
    "cuerpo","corazón","corazon","sangre","dolor","salud","hambre","sueño","sueno","miedo","suerte",
    "verdad","razón","razon","historia","realidad","futuro","pasado","momento","lugar","forma","parte",
    "cambio","orden","nivel","grupo","número","numero","línea","linea","punto","ejemplo","manera","caso",
}

VOWEL_MAP = str.maketrans({"á":"a","é":"e","í":"i","ó":"o","ú":"u","ü":"u"})

@dataclass
class Entry:
    rank: int
    word: str
    count: int
    hunspell: bool
    letters: str
    length: int
    accented: bool
    has_enye: bool
    tier: str
    reason: str


def download() -> None:
    subprocess.run(["curl","-fL","--retry","3","-o",str(FREQ_PATH),FREQ_URL], check=True)


def hunspell_words(words: list[str]) -> set[str]:
    proc = subprocess.run(
        ["hunspell","-d","es_ES","-l"],
        input="\n".join(words)+"\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    miss = {x.strip().lower() for x in proc.stdout.splitlines() if x.strip()}
    return {w for w in words if w.lower() not in miss}


def card_letters(word: str) -> str:
    return word.lower().translate(VOWEL_MAP)


def clean_candidate(word: str) -> tuple[bool,str]:
    w = unicodedata.normalize("NFC", word.lower())
    if len(w) < 3 or len(w) > 11:
        return False,"length"
    if not ALLOWED_CHARS.fullmatch(w):
        return False,"chars"
    if any(p.search(w) for p in DENY_PATTERNS):
        return False,"pattern"
    if w in DENY_EXACT:
        return False,"manual_deny"
    # Reject obvious clitic compounds and highly marked forms for beginner play.
    if len(w) >= 8 and any(w.endswith(s) for s in ("melo","mela","telos","telas","selos","selas","noslo","nosla")):
        return False,"clitic"
    return True,"base"


def assign_tier(rank: int, word: str, count: int) -> tuple[str,str]:
    w = word.lower()
    # Manual anchors override frequency artifacts.
    if w in A1_CORE or w in A1_FUNCTION:
        return "A1","manual_core"
    if w in A2_CORE:
        return "A2","manual_core"
    # Frequency proxy plus pedagogical morphology constraints.
    if rank <= 4500 and len(w) <= 8 and count >= 8000:
        if not any(w.endswith(x) for x in ("aría","erías","irías","aseis","ieseis","ásemos","iésemos")):
            return "A1_REVIEW","frequency_proxy"
    if rank <= 14000 and len(w) <= 10 and count >= 1200:
        return "A2_REVIEW","frequency_proxy"
    return "EXCLUDE","outside_scope"


def read_frequency() -> list[tuple[int,str,int]]:
    rows=[]
    with FREQ_PATH.open(encoding="utf-8") as f:
        for rank,line in enumerate(f,1):
            parts=line.rstrip("\n").rsplit(" ",1)
            if len(parts)!=2: continue
            word,count=parts
            try: count=int(count)
            except ValueError: continue
            rows.append((rank,unicodedata.normalize("NFC",word.lower()),count))
    return rows


def build() -> list[Entry]:
    raw=read_frequency()
    prelim=[]
    seen=set()
    for rank,w,count in raw:
        if w in seen: continue
        seen.add(w)
        ok,_=clean_candidate(w)
        if ok: prelim.append((rank,w,count))
    accepted=hunspell_words([w for _,w,_ in prelim])
    entries=[]
    for rank,w,count in prelim:
        hs=w in accepted
        if not hs: continue
        tier,reason=assign_tier(rank,w,count)
        letters=card_letters(w)
        entries.append(Entry(rank,w,count,hs,letters,len(letters),letters!=w,"ñ" in letters,tier,reason))
    return entries


def write_entries(entries: list[Entry]) -> None:
    fields=list(asdict(entries[0]).keys())
    with (OUT/"lexicon_audit.csv").open("w",encoding="utf-8",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=fields); wr.writeheader(); wr.writerows(asdict(e) for e in entries)
    for tier,name in [("A1","a1_core.csv"),("A1_REVIEW","a1_review_queue.csv"),("A2","a2_core.csv"),("A2_REVIEW","a2_review_queue.csv")]:
        rows=[e for e in entries if e.tier==tier]
        with (OUT/name).open("w",encoding="utf-8",newline="") as f:
            wr=csv.DictWriter(f,fieldnames=fields); wr.writeheader(); wr.writerows(asdict(e) for e in rows)
    # Formal playable sets: manual core + high-confidence reviewed proxy subset.
    a1=[e for e in entries if e.tier=="A1"]
    a1_proxy=[e for e in entries if e.tier=="A1_REVIEW"]
    a2=[e for e in entries if e.tier in {"A1","A2"}]
    a2_proxy=[e for e in entries if e.tier in {"A1_REVIEW","A2_REVIEW"}]
    # Keep scope practical and auditable; review queue remains separate.
    a1_final=sorted(a1,key=lambda e:e.rank) + sorted(a1_proxy,key=lambda e:e.rank)[:650]
    a2_final=sorted({e.word:e for e in (a2 + sorted(a2_proxy,key=lambda e:e.rank)[:1800])}.values(),key=lambda e:e.rank)
    for rows,name in [(a1_final,"a1_playable.csv"),(a2_final,"a2_playable.csv")]:
        with (OUT/name).open("w",encoding="utf-8",newline="") as f:
            wr=csv.DictWriter(f,fieldnames=fields); wr.writeheader(); wr.writerows(asdict(e) for e in rows)
    return a1_final,a2_final


def target_distribution(entries: list[Entry], total: int=106) -> dict[str,int]:
    # Weight each word by sqrt frequency to avoid top words dominating, then by inverse length.
    score=Counter()
    for e in entries:
        weight=math.sqrt(max(e.count,1))/max(e.length,3)
        score.update({ch:weight*n for ch,n in Counter(e.letters).items()})
    alphabet=list("aeosnrildtcumpbgvyhfqjñxzkw")
    # largest-remainder apportionment; require one each for letters represented in lexicon.
    present={c for c in alphabet if score[c]>0}
    base={c:(1 if c in present else 0) for c in alphabet}
    remain=total-sum(base.values())
    s=sum(score[c] for c in alphabet)
    quotas={c:(score[c]/s*remain if s else 0) for c in alphabet}
    for c in alphabet: base[c]+=int(math.floor(quotas[c]))
    left=total-sum(base.values())
    for c in sorted(alphabet,key=lambda c:quotas[c]-math.floor(quotas[c]),reverse=True)[:left]: base[c]+=1
    return {c.upper():base[c] for c in alphabet if base[c]>0}


def playable_rate(entries: list[Entry], dist: dict[str,int], trials: int=5000, hand=10, market=5, seed=42) -> dict:
    import random
    rng=random.Random(seed)
    deck=[k.lower() for k,n in dist.items() for _ in range(n)]
    words=[Counter(e.letters) for e in entries]
    start=0; after_swap=0
    dead_letters=Counter()
    for _ in range(trials):
        rng.shuffle(deck)
        h=Counter(deck[:hand]); m=Counter(deck[hand:hand+market])
        def canplay(hh,mm):
            for wc in words:
                own=sum(min(hh[c],n) for c,n in wc.items())
                missing=sum(max(0,n-hh[c]) for c,n in wc.items())
                if own>=2 and missing<=1 and all(wc[c] <= hh[c]+mm[c] for c in wc): return True
            return False
        ok=canplay(h,m)
        start+=ok
        if not ok:
            # Optimal one-card market swap approximation.
            found=False
            for give in list(h):
                if h[give]<=0: continue
                for take in list(m):
                    if m[take]<=0: continue
                    h2=h.copy();m2=m.copy();h2[give]-=1;h2[take]+=1;m2[take]-=1;m2[give]+=1
                    if canplay(h2,m2): found=True;break
                if found: break
            after_swap+=found
            if not found: dead_letters.update(h)
    return {"trials":trials,"start_playable_rate":start/trials,"rescued_by_one_swap_rate":after_swap/trials,"unresolved_rate":1-(start+after_swap)/trials,"dead_hand_letters":dead_letters.most_common()}


def optimize(entries: list[Entry], name: str) -> dict:
    initial=target_distribution(entries)
    best=initial.copy(); best_result=playable_rate(entries,best,trials=4000,seed=101)
    alphabet=list(best)
    # Coordinate hill climb: transfer one card from donor to recipient.
    improved=True; rounds=0
    while improved and rounds<4:
        improved=False; rounds+=1
        candidates=[]
        for donor in alphabet:
            if best.get(donor,0)<=1: continue
            for recv in alphabet:
                if donor==recv: continue
                d=best.copy();d[donor]-=1;d[recv]=d.get(recv,0)+1
                r=playable_rate(entries,d,trials=1800,seed=1000+rounds)
                candidates.append((r["unresolved_rate"],-r["start_playable_rate"],donor,recv,d,r))
        candidates.sort(key=lambda x:(x[0],x[1]))
        if candidates and (candidates[0][0] < best_result["unresolved_rate"]-0.001 or -candidates[0][1] > best_result["start_playable_rate"]+0.003):
            _,_,donor,recv,best,best_result=candidates[0]; improved=True
    final=playable_rate(entries,best,trials=12000,seed=2026)
    payload={"name":name,"initial_distribution":initial,"optimized_distribution":best,"final_metrics":final,"cards":sum(best.values())}
    (OUT/f"{name}_distribution.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    return payload


def main():
    download()
    entries=build()
    a1,a2=write_entries(entries)
    a1opt=optimize(a1,"a1")
    a2opt=optimize(a2,"a2")
    summary={
        "source_rows":sum(1 for _ in FREQ_PATH.open(encoding="utf-8")),
        "hunspell_valid_filtered":len(entries),
        "a1_playable":len(a1),
        "a2_playable":len(a2),
        "a1":a1opt,
        "a2":a2opt,
        "policy":{"length":"3-11","proper_names":"manual deny + frequency review","offensive":"manual deny","accents":"retained in orthography, stripped only for card signature","enye":"independent card"},
    }
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
