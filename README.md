# Pro gradu -tutkielman aineisto ja ohjelmistokoodi

Tämä GitHub-repositorio sisältää pro gradu -tutkielmassa käytetyn
aineiston, analyysikoodin sekä visualisointityökalun.

Repositorion avulla analyysi ja tulokset ovat mahdollisimman läpinäkyviä ja
toistettavia.

---

## Sisältö

Repositorio sisältää seuraavat kokonaisuudet:

### Aineisto
Aineistokansio sisältää tutkielmassa käytetyn datan eri käsittelyvaiheissa,
mukaan lukien:
- alkuperäinen CNKI-tietokannasta kerätty aineisto
- analyysia varten muokatut JSON/JSONL-tiedostot
- käännökset ja asiasanoitukset
- visualisointityökalua varten koottu lopullinen aineisto

Tiedostojen tarkempi kuvaus löytyy aineistokansiosta.

### Ohjelmistokoodi
Koodikansio sisältää Python-ohjelmat, joilla:
- raakadata on muunnettu analyysimuotoon
- aineistosta on luotu vektoriesityksiä
- klusterointi ja avainsana-analyysi on suoritettu
- aineisto on käännetty ja asiasanoitettu
- lopullinen visualisointiaineisto on koottu

Kaikki gradussa käytetty ohjelmistokoodi on tuotettu ChatGPT 5.2 -työkalulla,
pois lukien CNKI-aineiston raapiminen (Tulkki, 2025).

### Visualisointityökalu
Repositorio sisältää myös visualisointityökalun, jonka avulla aineistoa
voi tarkastella esimerkiksi:
- avainsanojen
- aikarajauksen
- teemojen ja klustereiden

Visualisointityökalu on ladattavissa pakattuna zip-tiedostona.
Windows-käyttäjät voivat käynnistää työkalun purkamalla paketin ja
suorittamalla `run_app.bat`-tiedoston.

---

## Toistettavuus ja tekniset huomiot

- Repositorio ei sisällä Python-virtuaaliympäristöä (`.venv`).
- Tarvittavat riippuvuudet on määritelty `requirements.txt`-tiedostossa.
- Käyttäjän tulee luoda oma virtuaaliympäristö ja asentaa riippuvuudet
  tarvittaessa.

Esimerkki:
```bash
python -m venv .venv
pip install -r requirements.txt

# Tutkielma

Varsinainen pro gradu -tutkielma on julkaistu erikseen, eikä se sisälly
tähän repositorioon. Tässä repositoriossa oleva materiaali toimii
tutkielman menetelmällisenä ja aineistollisena liitteenä.

# Lisätiedot

Tämä repositorio on tarkoitettu tutkimukselliseen ja opetukselliseen käyttöön.
