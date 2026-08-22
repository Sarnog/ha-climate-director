# Climate Director — Guide d'installation (Français)

[![Offrez-moi un café sur Ko-fi](https://img.shields.io/badge/Ko--fi-Offrez--moi%20un%20café-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Sponsoriser via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)

Ce guide explique pas à pas comment installer et configurer Climate Director.
Suivez simplement les étapes de haut en bas ; chaque étape s'appuie sur la
précédente.

## Sommaire

- [Qu'est-ce que Climate Director](#quest-ce-que-climate-director)
- [Ce dont vous avez besoin](#ce-dont-vous-avez-besoin)
- [Étape 1 — Installation](#étape-1--installation)
- [Étape 2 — Ajouter l'intégration](#étape-2--ajouter-lintégration)
- [Le menu principal](#le-menu-principal)
- [Étape 3 — Réglages généraux](#étape-3--réglages-généraux)
- [Étape 4 — Zones](#étape-4--zones)
- [Étape 5 — Sources](#étape-5--sources)
- [Étape 6 — Circuits de climatisation](#étape-6--circuits-de-climatisation)
- [Étape 7 — Sources de chaleur partagées](#étape-7--sources-de-chaleur-partagées)
- [Étape 8 — Groupes exclusifs](#étape-8--groupes-exclusifs)
- [Étape 9 — Fenêtres silencieuses](#étape-9--fenêtres-silencieuses)
- [Étape 10 — Résidents](#étape-10--résidents)
- [Étape 11 — Portes et fenêtres](#étape-11--portes-et-fenêtres)
- [Étape 12 — Enregistrer et fermer](#étape-12--enregistrer-et-fermer)
- [Ce que vous obtenez dans Home Assistant](#ce-que-vous-obtenez-dans-home-assistant)
- [Les interrupteurs et boutons](#les-interrupteurs-et-boutons)
- [Actions](#actions)
- [Préchauffage et pré-refroidissement](#préchauffage-et-pré-refroidissement)
- [Prendre la main](#prendre-la-main)
- [Évaluer une période en mode fantôme](#évaluer-une-période-en-mode-fantôme)
- [Blueprints et notifications](#blueprints-et-notifications)
- [Résoudre les problèmes](#résoudre-les-problèmes)
- [Langues](#langues)

## Qu'est-ce que Climate Director

Climate Director est une intégration Home Assistant qui pilote des appareils de
climatisation existants. Elle ne possède aucun matériel : elle dirige les
entités `climate` que vous avez déjà — une chaudière à gaz, une pompe à
chaleur, des climatiseurs. À chaque instant, elle calcule un état final
cohérent pour toute la maison et le traduit en appels de service.

**Le mode fantôme est activé par défaut.** L'intégration calcule alors chaque
décision et montre ce qu'elle aurait fait, mais ne pilote rien. Vous pouvez
ainsi la laisser tourner pendant des semaines à côté de vos automatisations
existantes et ne basculer qu'une fois votre confiance établie.

Trois concepts forment la base :

| Concept | Signification |
|---|---|
| **Zone** | Une pièce. Décrit *ce que vous voulez* : température cible, quand le chauffage ou le refroidissement peut démarrer, et en quelle saison. |
| **Source** | Un appareil capable de desservir une zone, avec une fonction (chauffer, refroidir ou les deux), un ordre de préférence et une fenêtre de température extérieure. |
| **Circuit de climatisation** | Une unité extérieure et les unités intérieures qui y sont raccordées. Décrit *ce qui est techniquement possible en même temps*. |

La règle d'or pour une unité extérieure partagée : toutes les unités
intérieures d'un circuit portent la même fonction — chauffer, refroidir, arrêt
ou simple ventilation. Deux unités intérieures sur une même unité extérieure ne
peuvent donc pas avoir l'une qui chauffe pendant que l'autre refroidit. Climate
Director sait quelles unités vont ensemble et résout ce conflit pour vous.

## Ce dont vous avez besoin

| Entité | Requis | Pour quoi |
|---|---|---|
| Une `climate.*` par zone | **oui** | sans appareil, il n'y a rien à piloter |
| Un capteur de température par zone | **oui** | sans mesure, l'intégration ne peut pas distinguer trop froid de trop chaud ; une `climate.*` avec `current_temperature` convient |
| `sensor.*` ou `weather.*` température extérieure | non | seulement pour borner par température extérieure — gaz sous 3 °C, pompe à chaleur au-dessus, par exemple |
| `weather.*` ou `sensor.*` précipitations | non | seulement si les précipitations peuvent lever la limite « ouvrir une fenêtre » |
| `person.*` ou `device_tracker.*` par résident | oui, dès que vous configurez des résidents | sinon ce résident ne peut jamais être présent |
| Un capteur de sommeil par résident | non | sans lui, personne ne compte jamais comme endormi |
| `binary_sensor.*` présence par zone | seulement si une zone fonctionne sur *la pièce elle-même* | c'est alors la seule porte de la zone |
| `binary_sensor.*` porte ou fenêtre | non | suspend les zones liées tant qu'il est ouvert |
| `calendar.*` | non | active le programme vacances tout seul ; ne fonctionne qu'avec un mot-clé |
| Une entité de saison | non | seulement si vous ne voulez pas déduire la saison du mois |

Vous n'avez aucun helper à créer. L'intégration fabrique elle-même tous ses
interrupteurs et réglages.

## Étape 1 — Installation

**Version minimale :** Home Assistant **2025.3** ou plus récent. L'intégration
ajoute ses entités via une API disponible depuis 2025.3.

**Via HACS** (recommandé) :

1. Ouvrez HACS.
2. Allez sur les trois points en haut à droite et choisissez **Dépôts
   personnalisés**.
3. Ajoutez cette URL, avec la catégorie **Intégration** :

   ```
   https://github.com/Sarnog/ha-climate-director
   ```

4. Cherchez **Climate Director** dans HACS, installez, puis redémarrez Home
   Assistant.

**Manuellement :**

1. Téléchargez ou clonez ce dépôt.
2. Copiez le dossier `custom_components/climate_director` dans le dossier
   `custom_components` de votre configuration Home Assistant.
3. Redémarrez Home Assistant.

## Étape 2 — Ajouter l'intégration

1. Allez dans **Réglages → Appareils et services → Ajouter une intégration**.
2. Cherchez **Climate Director** et choisissez-le.
3. Donnez un **nom** à l'installation. Ce nom devient le titre et précède le
   nom de chaque entité créée par l'intégration.
4. Laissez le **Mode fantôme** activé. Vous observez ainsi d'abord avant que
   quoi que ce soit soit réellement piloté.
5. Enregistrez. L'installation apparaît dans l'onglet **Intégrations**.

Tout le reste se construit sous **Configurer** sur cette intégration.

## Le menu principal

Sous **Configurer** se trouve le menu principal, dans cet ordre :

| Menu | Pour quoi |
|---|---|
| **Réglages généraux** | température extérieure, saison, portes, fenêtres, calendriers, mode fantôme |
| **Zones et sources** | par pièce : température, points de démarrage et d'arrêt, et les appareils associés |
| **Circuits de climatisation** | quelles unités intérieures partagent une unité extérieure |
| **Sources de chaleur partagées** | une chaudière ou pompe à chaleur desservant plusieurs pièces |
| **Groupes exclusifs** | des appareils qui ne doivent jamais tourner ensemble |
| **Fenêtres silencieuses** | heures où le directeur ne démarre rien de lui-même |
| **Résidents** | qui est présent, qui dort, et l'emploi du temps de chacun |
| **Portes et fenêtres** | quelles ouvertures mettent quelles zones en pause |
| **✅ Enregistrer et fermer** | rien n'est réellement enregistré avant cet endroit |

Deux choses rendent le menu agréable :

- Chaque écran se termine par **Quand vous avez terminé ici**, avec le choix
  *Conserver ces modifications et revenir* ou *Annuler et revenir*.
- Chaque liste comporte une ligne **← Retour au menu principal**.

Rien ne vous piège donc. Revenir en arrière fonctionne toujours, même avec un
écran à moitié rempli — ce que vous avez tapé est alors perdu. Et **rien**
n'est enregistré tant que vous n'avez pas choisi **Enregistrer et fermer** dans
le menu principal.

## Étape 3 — Réglages généraux

| Réglage | Ce qu'il fait |
|---|---|
| **Capteur de température extérieure** | alimente chaque limite extérieure. Sans capteur, toute limite compte comme non atteinte et l'installation reste immobile |
| **Système de chauffage** | *Centralisé* ou *Par zone*, voir ci-dessous |
| **Source de la saison** | d'où vient la saison : le mois, une entité, ou fixée été/hiver |
| **Entité de saison** | seulement si la source est réglée sur *entité* ; l’entité intégrée `season.*` est aussi sélectionnable |
| **Hémisphère** | quels mois comptent comme été lorsque la saison vient du mois : nord avril–septembre, sud octobre–mars |
| **Choix de saison** | l'entité `select.*` *Saison* règle la saison à la main sur Automatique, Été ou Hiver ; le choix survit à un redémarrage |
| **Quelqu'un à la maison doit être réveillé** | activé = la maison attend quelqu'un à la maison *et* réveillé ; désactivé = le sommeil ne compte pas |
| **L'emploi du temps d'un résident doit être ouvert** | activé = la maison attend la première fenêtre d'emploi du temps ; désactivé = la présence seule décide |
| **Calendriers de vacances** | quels calendriers peuvent annoncer des vacances ; plusieurs autorisés |
| **Mot qui marque des vacances** | le mot-clé que doit porter un événement ; vide = calendriers ignorés |
| **Préchauffage de / jusqu'à** | la fenêtre dans laquelle une demande de préchauffage compte ; par défaut 06:00–23:00 |
| **Durée de préchauffage** | le plafond d'une seule demande ; par défaut 120 minutes |
| **Mode invités de / jusqu'à** | la fenêtre où le mode invités s'applique ; les deux vides = toute la journée |
| **Signaler une zone bloquée après** | après combien de minutes d'attente une zone compte comme bloquée ; 0 éteint le capteur |
| **Source de précipitations** | une entité `weather.*` ou `sensor.*` qui dit s'il y a des précipitations ; vide = la règle de précipitations ne participe pas |
| **États comptant comme précipitations** | quels états de cette entité signifient des précipitations ; pluie, neige et grêle par défaut |
| **Combien de temps les précipitations continuent de compter (minutes)** | délai de grâce après l'arrêt des précipitations ; 15 minutes par défaut |
| **Mode fantôme** | activé = tout calculer, ne rien piloter |

### Les précipitations mettent la limite extérieure de côté

La limite extérieure par zone est une règle d'économie avec un postulat : s'il
fait meilleur dehors que dedans, vous avez intérêt à ouvrir une fenêtre plutôt
que d'allumer le climatiseur. Quand il y a des précipitations, cette fenêtre
reste fermée, donc rien ne se passe, alors que la pièce reste trop chaude ou
trop froide.

Configurez donc une **source de précipitations**. Tant qu'elle signale des
précipitations, Climate Director ignore la **limite extérieure par zone** —
exactement
comme le fait une demande de préchauffage. La bande morte, la saison et la
limite extérieure **par source** continuent de s'appliquer ; ce sont elles qui
choisissent l'appareil. Le délai de grâce fait qu'une averse de cinq minutes ne
fait pas osciller la régulation. Sans source, la règle de précipitations ne
participe pas.

Une pièce sans fenêtres n'y gagne rien. Là, activez dans la zone **Les
précipitations ne lèvent pas la règle « ouvrir une fenêtre »**, et la limite
extérieure continue de s'appliquer même lorsqu'il y a des précipitations.

### Système de chauffage : centralisé ou par zone

| Choix | Ce qu'il signifie | Comment le remplir |
|---|---|---|
| **Centralisé** | Une source de chaleur pour toute la maison. Allumer pour une pièce réchauffe le reste avec. Pensez à un seul thermostat intelligent, avec ou sans robinets de radiateur. | Mettez le **même** thermostat comme source sous chaque zone |
| **Par zone** | Chaque partie de la maison peut recevoir sa chaleur séparément, via une vanne de zone ou une source propre. | Donnez à chaque zone sa **propre** vanne ou son appareil comme source ; s'il y a une chaudière partagée, ajoutez-la comme source de chaleur partagée |

Des robinets de radiateur intelligents seuls ne sont pas un zonage : la maison
a encore un circuit et une source de chaleur qui s'allume ou s'éteint pour tout
le monde en même temps. Choisissez alors **Centralisé**. Une chaudière avec
trois vannes de zone est en revanche **Par zone**.

Ce réglage ne change rien à qui peut tourner. Il consigne ce qu'est votre
installation, pour que le contrôle de configuration puisse vous avertir si
votre montage ne correspond pas.

## Étape 4 — Zones

Une zone est une pièce. Par zone, vous réglez :

| Réglage | Ce qu'il fait |
|---|---|
| **Nom** | le libellé qui apparaît partout |
| **Capteur de température intérieure** | ce sur quoi la bande morte calcule ; une `climate.*` qui mesure elle-même convient |
| **Préséance sur une unité extérieure partagée** | avec quelle force cette zone revendique une unité extérieure partagée ; **le plus petit gagne**. Sur un circuit, aucun numéro ne peut apparaître deux fois |
| **Ce qui décide si cette zone tourne** | *le foyer* (emploi du temps, sommeil, quelqu'un à la maison) ou *la pièce elle-même* (seul le capteur de présence) |
| **Capteur de présence + état + délai de grâce** | quand la pièce compte comme occupée ; le délai absorbe les détecteurs qui clignotent |
| **Les précipitations ne lèvent pas la règle « ouvrir une fenêtre »** | activé pour une pièce sans fenêtres ; là, la limite extérieure continue de s'appliquer même lorsqu'il y a des précipitations |
| **Cette zone peut chauffer** | désactivé = cette pièce n'est jamais chauffée |
| **Température cible chauffage** | la consigne donnée à l'appareil quand le chauffage tourne — pas le point de démarrage |
| **Démarrer le chauffage à** | le chauffage démarre à cette température intérieure ou en dessous |
| **Bande morte chauffage** | à quelle distance au-dessus du point de démarrage le chauffage s'arrête |
| **Chauffer seulement sous cette température extérieure** | au-dessus, le chauffage reste éteint ; vide = aucune limite |
| **Cette zone peut refroidir** | désactivé = cette pièce n'est jamais refroidie |
| **Température cible refroidissement** | la consigne donnée à l'appareil quand le refroidissement tourne |
| **Démarrer le refroidissement à** | le refroidissement démarre à cette température intérieure ou au-dessus |
| **Bande morte refroidissement** | à quelle distance sous le point de démarrage le refroidissement s'arrête |
| **Refroidir seulement au-dessus de cette température extérieure** | en dessous, le refroidissement reste éteint ; vide = aucune limite |
| **Refroidir seulement en été** | lie le refroidissement à la saison des réglages généraux |

### Comment fonctionne la bande morte

L'allumage et l'extinction se font à deux températures différentes, pour qu'un
appareil ne cliquette pas sur un dixième de degré :

- le chauffage démarre à `intérieur ≤ point de démarrage` et s'arrête à `intérieur ≥ point de démarrage + bande` ;
- le refroidissement démarre à `intérieur ≥ point de démarrage` et s'arrête à `intérieur ≤ point de démarrage − bande`.

Le point de démarrage compte comme atteint, le point d'arrêt comme dépassé. Un
degré de bande est un bon début.

### Ce que l'écran refuse

Trois combinaisons sont refusées à l'enregistrement, car elles produisent une
zone qui existe mais ne fait jamais rien :

- une **cible du mauvais côté du point de démarrage** — l'appareil reçoit alors
  une température pour laquelle il n'a rien à faire ;
- un **refroidissement qui démarre au niveau ou sous le point où le chauffage
  démarre** — les deux demandent alors la même pièce en même temps ;
- la zone réglée sur **la pièce elle-même sans capteur de présence**, ou une
  zone qui **ne peut ni chauffer ni refroidir**.

### Le foyer ou la pièce elle-même

- **Le foyer** (par défaut) : emploi du temps, sommeil et quelqu'un-à-la-maison
  comptent. Ajoutez un capteur de présence et il agit comme condition
  supplémentaire : le foyer doit l'autoriser **et** la pièce doit être occupée.
- **La pièce elle-même** : emploi du temps, sommeil et quelqu'un-à-la-maison
  sont ignorés. Seul le capteur de présence décide. Cela exige donc un capteur
  de présence, sinon la zone ne peut jamais tourner.

Ainsi, une pièce peut suivre l'emploi du temps et une autre la présence.

## Étape 5 — Sources

Une source est un appareil capable de desservir la zone. Après avoir enregistré
une zone, vous choisissez immédiatement ses sources.

| Réglage | Ce qu'il fait |
|---|---|
| **Entité climatique** | l'appareil lui-même |
| **Ce que cet appareil peut faire** | chauffer seulement, refroidir seulement, ou les deux. Une chaudière est *chauffage seulement* |
| **Démarrer cet appareil automatiquement** | désactivé le laisse tranquille, voir ci-dessous |
| **Ordre dans cette zone** | quelle source est préférée ; **le plus petit gagne** |
| **Utiliser à partir de cette température extérieure** | la borne inférieure ; incluse dans la plage |
| **Utiliser jusqu'à cette température extérieure** | la borne supérieure ; exclue de la plage |

### Bornes extérieures : à moitié ouvertes

La borne inférieure appartient à la fenêtre, la supérieure non. Deux sources
adjacentes couvrent ainsi toute l'échelle, sans trou ni chevauchement.

Vous voulez le gaz sous 3 °C et le climatiseur au-dessus ? Ne mettez alors
**pas** la frontière à 3,0 :

| Frontière | 2,9 °C | 3,0 °C | 3,1 °C |
|---|---|---|---|
| les deux à `3.0` | gaz | **climatiseur** | climatiseur |
| les deux à `3.1` | gaz | **gaz** | climatiseur |

Réglez la frontière de la même façon sur **chaque** source, et jamais
différemment — sinon un chevauchement apparaît où les deux sont autorisés.

### Un appareil que vous allumez vous-même

Désactivez **Démarrer cet appareil automatiquement** pour un appareil que vous
manœuvrez à la main (un climatiseur dans une chambre sans capteur de présence,
par exemple). Le directeur :

- **ne l'allume jamais**, quelle que soit la température de la pièce ;
- **le laisse** tel que vous l'avez réglé ;
- **ne l'éteint que** lorsqu'il exécute une fonction que l'unité extérieure
  partagée ne peut pas admettre.

Si une fonction ne peut être assurée que par un tel appareil, l'intégration le
signale une fois sous *Réparations*. Confirmez l'avis et il ne reviendra pas —
même après un redémarrage. Si la zone gagne plus tard une nouvelle fonction
manuelle, un nouvel avis suivra.

## Étape 6 — Circuits de climatisation

Nécessaire seulement quand des unités intérieures partagent une unité
extérieure. Si chaque unité a la sienne, laissez vide.

| Réglage | Ce qu'il fait |
|---|---|
| **Nom** | un libellé pour distinguer les circuits |
| **Unités intérieures** | quelles entités `climate.*` sont raccordées à cette unité extérieure. Incluez aussi les unités que le directeur ne gère pas : elles réclament le compresseur également |
| **Peut chauffer et refroidir en même temps** | désactivé pour un multi-split ordinaire ; activé pour un split simple ou un VRF trois tubes à récupération de chaleur |
| **Règle de conflit** | qui gagne quand deux pièces veulent des fonctions opposées |
| **Une zone perdante peut ventiler** | activé = la perdante passe en `fan_only` au lieu de s'éteindre, mais seulement si l'unité connaît ce mode ; sinon elle s'éteint |
| **Pause lors du changement de fonction** | combien de temps tout reste éteint avant le basculement |
| **Durée minimale avant un changement de fonction** | combien de temps une fonction doit avoir tourné avant que l'autre puisse prendre le relais |
| **Repos avant qu'une unité puisse redémarrer** | ne retarde que les démarrages, jamais les arrêts ; par défaut 180 secondes |
| **Nombre maximal d'unités en marche** | la limite de capacité de l'unité extérieure ; vide = pas de plafond |

### Règles de conflit

| Règle | Comportement |
|---|---|
| **Priorité** (par défaut) | la zone au numéro de priorité le plus petit gagne |
| **Premier arrivé** | la fonction déjà en cours garde le circuit ; une nouvelle demande attend |
| **Demande** | l'écart le plus grand à la consigne gagne |
| **Saison** | la saison dicte la fonction ; tout ce qui va dans l'autre sens s'efface |

## Étape 7 — Sources de chaleur partagées

Une chaudière ou pompe à chaleur sur laquelle plusieurs pièces tirent via leurs
propres vannes. Laissez vide si le système allume son propre brûleur dès qu'une
vanne le demande.

| Réglage | Ce qu'il fait |
|---|---|
| **Nom** | un libellé pour distinguer les sources de chaleur |
| **Entité climatique** | la chaudière ou pompe à chaleur elle-même ; ne doit pas aussi être source d'une zone, sinon elle recevrait deux ordres |
| **Zones qu'elle dessert** | vide = toutes les pièces |
| **Température cible fixe** | vide = elle suit la cible la plus chaude parmi les pièces qui demandent |

La source de chaleur tourne tant qu'une pièce qu'elle dessert est chauffée, et
s'arrête dès qu'il n'y en a plus.

## Étape 8 — Groupes exclusifs

Vous voulez que deux appareils ne tournent **jamais** en même temps — une
chaudière à gaz et une pompe à chaleur, par exemple ? Ne confiez pas cela aux
seules bornes extérieures. Une valeur laissée en arrière suffit à les faire
s'allumer ensemble. Mettez-les plutôt dans un groupe exclusif : des appareils
d'un groupe, un seul tourne à la fois.

Attention à ce qu'un groupe signifie : **un** appareil du groupe à la fois. Si
vous voulez que la chaudière à gaz ne gêne aucun climatiseur, tandis que deux
climatiseurs du même circuit peuvent refroidir ensemble, faites un groupe par
paire — le gaz avec l'un, le gaz avec l'autre.

Un groupe lie aussi les appareils que vous allumez vous-même : quand un autre
membre du groupe vient à son tour, l'appareil manuel s'éteint. Et dans
l'autre sens : quand un tel appareil tourne déjà, il occupe le groupe et un
autre membre attend.

## Étape 9 — Fenêtres silencieuses

Des heures où le directeur **ne démarre rien de lui-même**. Rentrer à onze
heures du soir alors que vous allez vous coucher ne doit pas lancer la
chaudière.

C'est un frein au **démarrage**, pas à la poursuite :

- ce qui tourne déjà reste régulé ;
- allumez quelque chose vous-même et c'est repris ;
- ce qui est éteint le reste jusqu'à la fin de la fenêtre.

Les fenêtres peuvent franchir minuit et portent des jours de semaine. Un foyer
qui se couche à neuf heures en semaine et à onze heures le week-end en règle
deux :

| De | Jusqu'à | Jours |
|---|---|---|
| 21:00 | 09:00 | lun mar mer jeu dim |
| 23:00 | 09:00 | ven sam |

Sans fenêtre réglée, le frein n'agit pas.

## Étape 10 — Résidents

Laissez vide pour un bâtiment où personne n'est suivi ; les portes de présence
sont alors ignorées au lieu de tout bloquer pour toujours.

| Réglage | Ce qu'il fait |
|---|---|
| **Nom** | un libellé pour distinguer les résidents |
| **Capteur de présence** | en général une `person.*` ; dit si ce résident est à la maison |
| **Capteur de sommeil** | quand ce résident dort ; vide = sommeil non suivi |
| **État signifiant endormi** | l'état que le capteur de sommeil rapporte pendant le sommeil |
| **Le capteur de sommeil compte de / jusqu'à** | les heures où ce capteur signifie quelque chose ; les deux vides = toute la journée |
| **Jours de la fenêtre de sommeil** | les jours où cette fenêtre s'applique ; vide = tous les jours |

### Emplois du temps

Après avoir enregistré un résident, vous réglez ses emplois du temps :

| Réglage | Ce qu'il fait |
|---|---|
| **C'est une fenêtre de vacances** | ne s'applique que pendant le programme vacances, en remplaçant alors les fenêtres ordinaires |
| **De / Jusqu'à** | la fenêtre ; peut franchir minuit |
| **Jours** | vide = chaque jour |

Un résident sans emploi du temps ne participe pas à la porte d'emploi du temps.
Quelqu'un sans fenêtre un jour donné ne retient pas la maison ce jour-là.

### Capteur de sommeil : pas de capteur, mais un bouton ?

Un bouton (`button` ou `input_button`) ne peut pas dire si vous dormez — son
état est l'instant du dernier appui. Ce qui fonctionne est un `input_boolean`
que vous basculez avec un bouton : créez l'interrupteur, choisissez-le comme
capteur de sommeil avec `on` comme état d'endormissement, et laissez un bouton
le basculer. Qui possède un vrai capteur de sommeil (un capteur de lit, un
chargeur sans fil) utilise celui-ci : c'est plus précis.

Laissez le capteur de sommeil vide et ce résident ne compte jamais comme
endormi.

## Étape 11 — Portes et fenêtres

Une ouverture restée ouverte assez longtemps suspend les zones concernées.

| Réglage | Ce qu'il fait |
|---|---|
| **Capteur** | le contact de porte ou de fenêtre ; ouvert compte comme `on` |
| **Zones concernées** | vide = toute l'installation |
| **Délai avant suspension** | vide ou 0 = dès l'ouverture |

## Étape 12 — Enregistrer et fermer

Choisissez **✅ Enregistrer et fermer** dans le menu principal. C'est seulement
là que l'installation est écrite.

Si quelque chose est structurellement faux — une zone sans source utilisable,
deux sources sur la même entité, une fenêtre extérieure qui n'admet rien —
vous voyez d'abord une liste, avec le choix *Enregistrer quand même* ou
*Revenir pour modifier quelque chose*. C'est un **avertissement, pas un refus** :
une installation peut délibérément être inhabituelle, et vous seul savez si
c'est le cas. La même liste apparaît aussi sous **Réparations** tant qu'elle
s'applique.

## Ce que vous obtenez dans Home Assistant

Un appareil par installation, avec en dessous :

| Entité | Pour quoi |
|---|---|
| `sensor.*_last_decision` | combien de zones sont desservies, avec le plan complet en attributs |
| `sensor.*_would_command_<entity>` | le mode dans lequel le directeur mettrait cet appareil — un capteur par appareil |
| `sensor.*_mismatch` | combien d'appareils se trouvent ailleurs que là où le plan les veut ; 0 = directeur et maison d'accord |
| `sensor.*_<zone>_source` | quelle source dessert cette zone, avec ce que la zone voulait, a obtenu et pourquoi |
| `binary_sensor.*_<zone>_blocked` | activé quand une zone a reçu moins que demandé, ou voulait tourner mais qu'une circonstance l'a retenue ; les portes fermées sont dans les attributs |
| `binary_sensor.*_<zone>_on_stand_in` | activé quand une zone tourne sur un appareil de secours parce que le premier choix est injoignable |
| `binary_sensor.*_stuck` | activé quand une zone reste trop longtemps sur le même motif d'attente |
| `switch.*_director` | l'interrupteur principal ; éteint = rien n'est régulé |
| `switch.*_holiday_schedule` | fait compter chaque jour comme un samedi, ou comme son propre programme vacances |
| `switch.*_guest_mode` | continue de réguler pendant que les résidents sont absents |
| `switch.*_<zone>_override` | rend une zone entièrement à vous |
| `number.*_<zone>_priority` | la préséance de cette zone ; réglable aussi depuis une automatisation |
| `number.*_pre_conditioning_duration` | combien de temps dure un appui sur un bouton de préchauffage |
| `button.*_<zone>_pre_condition` | préchauffe ou pré-refroidit cette zone |

Il existe aussi un export de diagnostic téléchargeable avec la configuration,
le dernier instantané lu et le dernier plan.

## Les interrupteurs et boutons

- **Interrupteur principal** (`switch.*_director`) : éteint = le directeur ne
  fait rien du tout.
- **Mode invités** (`switch.*_guest_mode`) : quelqu'un de non suivi loge là,
  donc « maison vide » ne dit rien. Le sommeil des présents s'applique toujours,
  et hors de la fenêtre invités, les portes ordinaires reprennent le relais.
- **Programme vacances** (`switch.*_holiday_schedule`) : chaque jour compte
  comme un samedi, ou comme sa propre fenêtre de vacances. S'active aussi tout
  seul dès qu'un calendrier configuré a un événement en cours portant le
  mot-clé. Sans mot-clé, les calendriers sont ignorés.
- **Override** (`switch.*_<zone>_override`) : rend une zone entièrement à vous.
  Le directeur n'envoie plus rien à cette zone — pas même un arrêt. Les règles
  de circuit s'appliquent toujours aux autres pièces. L'override expire de
  lui-même dès que tous les présents vont se coucher ou que la maison est vide.
- **Bouton de préchauffage** (`button.*_<zone>_pre_condition`) et **durée**
  (`number.*_pre_conditioning_duration`) : voir ci-dessous.

## Actions

| Action | Pour quoi |
|---|---|
| `climate_director.evaluate` | décider à nouveau tout de suite, sans attendre un changement d'état |
| `climate_director.precondition` | démarrer le préchauffage ou le pré-refroidissement |
| `climate_director.cancel_precondition` | annuler une demande de préchauffage en cours |

`climate_director.evaluate` est pratique pendant la mise en place. En mode
fantôme, il n'exécute toujours rien — il recalcule seulement.

## Préchauffage et pré-refroidissement

La seule façon de faire tourner une maison vide, et délibérément la seule que
vous devez activer à la main.

- **Avec un bouton** : chaque zone a `button.*_<zone>_pre_condition`. La durée
  d'un tel appui se règle dans `number.*_pre_conditioning_duration` (60 minutes
  par défaut, d'un quart d'heure à deux heures).
- **Avec l'action** :

  ```yaml
  action: climate_director.precondition
  data:
    zone_ids: [<zone>]
    minutes: 45
  ```

**Important :** vous ne dites pas ce qui doit se passer. La demande ouvre
seulement la porte ; ensuite l'intégration décide exactement comme d'habitude —
la bande morte vérifie s'il fait trop froid ou trop chaud, la saison et la
fenêtre extérieure par source choisissent l'appareil. Si la pièce est déjà
bien, l'appareil reste éteint.

Pendant une demande de préchauffage, l'interrupteur principal, un override, la
bande morte, la saison, la fenêtre extérieure par source, les fenêtres et
portes, le circuit et les groupes exclusifs continuent de s'appliquer. Sont
ignorés : *quelqu'un à la maison*, *réveillé*, *emploi du temps*, *présence dans
la pièce*, la fenêtre extérieure par zone et la fenêtre silencieuse.

Une fenêtre ou une porte ouverte **refuse** une demande. Celui qui a ouvert la
fenêtre peut dire : faites-le quand même.

```yaml
action: climate_director.precondition
data:
  zone_ids: [<zone>]
  minutes: 90
  ignore_openings: true
```

Deux limites impossibles à oublier :

- **Cela expire tout seul.** Demandez plus long que le maximum configuré et
  votre demande est raccourcie. Ne donner aucune durée donne le maximum.
- **Cela ne compte que dans la fenêtre** (06:00–23:00 par défaut). En dehors,
  une demande ne compte pas.

Annulez avec `climate_director.cancel_precondition`.

## Prendre la main

- **Éteindre un appareil vous-même** (sur l'appareil ou la télécommande) met la
  zone en silence. Le directeur ne le rallume pas deux secondes plus tard. La
  zone reprend dès que vous la rallumez, dès que tous les présents vont se
  coucher, ou dès le lendemain.
- **Allumer un appareil à la main pour quelques heures** fonctionne avec un
  script à côté, à condition de vous rendre la zone avec l'override pendant la
  durée. Sans override, le directeur recalcule son propre plan à la prochaine
  évaluation et éteint votre appareil. Un appareil avec *Démarrer cet appareil
  automatiquement* désactivé n'a pas besoin d'override.
- **Une pièce que vous manœuvrez toujours vous-même** : faites-en tout de même
  une zone (sinon l'intégration ignore cet appareil), choisissez l'entité
  `climate.*` de l'appareil comme capteur intérieur, et désactivez *Démarrer
  cet appareil automatiquement* sur la source.

## Évaluer une période en mode fantôme

Trois capteurs rendent une période en mode fantôme évaluable après coup :

- **`sensor.*_mismatch`** est le chiffre clé. Zéro signifie que le directeur est
  d'accord avec ce qui tourne à ce moment. Un pic bref est normal ; une valeur
  qui persiste est un vrai désaccord. Mettez ce capteur dans un graphique
  d'historique.
- **`sensor.*_would_command_<entity>`** se place à côté de l'historique de
  l'entité `climate` du même nom. Deux lignes qui se suivent = le directeur a
  décidé la même chose que vos automatisations.
- **`sensor.*_<zone>_source`** et **`binary_sensor.*_<zone>_blocked`** disent
  ensuite *pourquoi* : quelle source a été choisie, et quelle porte a retenu une
  zone.

## Blueprints et notifications

Climate Director n'envoie aucun message lui-même. Où va une notification,
comment elle sonne et si elle peut arriver la nuit diffère d'un foyer à
l'autre. L'intégration met plutôt en place des événements et des capteurs
auxquels accrocher votre propre automatisation. Trois d'entre eux sont à ne pas
sauter :

| Blueprint | Pourquoi vous ne pouvez pas vous en passer | Lien d'import |
|---|---|---|
| **Surveillance** | signale une panne silencieuse : une zone bloquée, ou une zone tournant sur un appareil de secours plus coûteux | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/monitoring.yaml` |
| **Préchauffage refusé** | vous avez appuyé sur un bouton et rien ne s'est passé ; celui-ci le signale, avec un bouton *Faites-le quand même* | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/precondition_refused.yaml` |
| **Ce qui a été décidé** | l'outil le plus pratique pendant la configuration et en mode fantôme | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/decisions.yaml` |

L'import passe par **Réglages → Automatismes et scènes → Blueprints → Importer
un blueprint**, avec le lien ci-dessus.

> **Importer seul ne suffit pas.** Un blueprint est un modèle ; rien n'écoute
> tant que vous n'en avez pas fait une automatisation. Faites-le tout de suite
> après l'import.

Tant que personne n'écoute une demande de préchauffage refusée, Home Assistant
affiche un avis de réparation à ce sujet. Il disparaît de lui-même dès qu'une
automatisation repose sur cet événement.

## Résoudre les problèmes

- **`binary_sensor.*_stuck`** s'allume quand une zone reste trop longtemps sur
  le même motif d'attente (15 minutes par défaut), ou quand une entité
  configurée est illisible — mal tapée, supprimée ou temporairement
  `unavailable`. Les entités concernées sont dans l'attribut
  `unusable_entities`. Un capteur lisible mais qui ne donne aucun nombre y
  figure aussi (`no number`).
- **`binary_sensor.*_<zone>_on_stand_in`** s'allume quand une zone tourne sur
  une source qui n'était pas le premier choix, parce que le premier choix est
  injoignable. La pièce devient simplement chaude — et c'est exactement
  pourquoi, sans capteur, vous ne remarquez rien avant la facture d'énergie.
- **Les avis de réparation** sous *Réparations* montrent les erreurs
  structurelles de la configuration. Les zones saines continuent d'être
  régulées ; une zone cassée n'arrête pas l'installation.
- **Le diagnostic** (téléchargeable sur l'intégration) contient la
  configuration, le dernier instantané lu et le dernier plan. Avec ces trois
  éléments, toute décision est exactement reproductible.

## Langues

L'explication sous chaque champ suit la langue de votre Home Assistant.
Fournies : néerlandais, anglais, allemand, français, espagnol et arabe.

[![Offrez-moi un café sur Ko-fi](https://img.shields.io/badge/Ko--fi-Offrez--moi%20un%20café-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Sponsoriser via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)
