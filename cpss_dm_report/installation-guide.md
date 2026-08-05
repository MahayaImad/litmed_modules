# Guide d'Installation - Module Rapport Dispositifs Médicaux

## 📁 Structure du Module

```
cpss_dm_report/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── product_template.py
├── wizard/
│   ├── __init__.py
│   └── cpss_dm_report_wizard.py
├── views/
│   ├── product_views.xml
│   └── wizard_views.xml
├── data/
│   └── product_category_data.xml
├── security/
│   └── ir.model.access.csv
└── static/
    └── description/
        └── icon.png
```

## 🔧 Installation

### 1. Prérequis
```bash
pip install xlsxwriter
```

### 2. Copier le module
Copiez le dossier `cpss_dm_report` dans votre répertoire d'addons Odoo.

### 3. Mettre à jour la liste des modules
- Allez dans **Applications**
- Cliquez sur **Mettre à jour la liste des applications**

### 4. Installer le module
- Recherchez "Dispositifs Médicaux" ou "cpss_dm_report"
- Cliquez sur **Installer**

## 📋 Configuration

### Étape 1: Activer le suivi par lots
1. **Inventaire** → **Configuration** → **Paramètres**
2. Activez **Numéros de lots et numéros de série**
3. Activez **Dates d'expiration** (pour les dates de péremption)

### Étape 2: Créer/Configurer un produit Dispositif Médical
1. Allez dans **Dispositifs Médicaux** → **Produits**
2. Créez un nouveau produit ou modifiez un existant
3. Dans l'onglet **Dispositif Médical**:
   - ✅ Cochez "Est un Dispositif Médical"
   - Renseignez la "Désignation du Dispositif Médical"
   - Sélectionnez le "Pays d'Origine"
   - Saisissez le "Type de Certification" (ex: CE, ISO 13485)
   - Sélectionnez le "Fabricant"

### Étape 3: Configurer le packaging (conditionnement)
1. Dans la fiche produit, onglet **Inventaire**
2. Section **Conditionnement**
3. Ajoutez les packagings (ex: "Boîte de 100", "Carton de 12")

## 🖨️ Générer le Rapport

### Accès au rapport
1. Menu **Dispositifs Médicaux** → **Rapports** → **Rapport Mensuel (Excel)**

### Paramètres du rapport
- **Date Début**: Premier jour de la période
- **Date Fin**: Dernier jour de la période
- **Société**: Sélectionnez votre entreprise (si multi-société)

### Génération
1. Cliquez sur **Générer le Rapport Excel**
2. Le fichier se télécharge automatiquement

## 📊 Colonnes du Rapport Excel

| Colonne | Source Odoo |
|---------|-------------|
| ETABLISSEMENT PHARMACEUTIQUE | Partner du picking (client/fournisseur) |
| DESIGNATION DU DM | Champ `medical_device_designation` ou nom produit |
| DENOMINATION COMMERCIALE | Nom du produit (`product.product`) |
| CONDITIONNEMENT | Premier packaging du produit |
| SOCIETE LABORATOIRE FABRICANT | Champ `manufacturer_id` |
| PAYS D'ORIGINE ET CERTIFICATION | `country_origin_id` + `certification_type` |
| DATE DE FABRICATION | Date création du lot |
| DATE DE PEREMPTION | `expiration_date` ou `use_date` du lot |
| N° DE LOTS | Nom du lot (`stock.lot`) |
| QUANTITE EN STOCK | Quantité disponible actuelle |
| QTE LIVREE AUX CLIENTS | Quantité du mouvement (sorties) |
| A LA DATE DU | Date du mouvement de stock |
| OBSERVATION | "Entrée" ou "Sortie" |

## ⚠️ Notes Importantes

1. **Seuls les produits marqués "Est un Dispositif Médical"** apparaissent dans le rapport.

2. **Les mouvements internes** (transferts entre entrepôts) ne sont pas inclus.

3. **Pour les dates de fabrication/péremption**: Assurez-vous que le module `product_expiry` est installé et que les lots ont leurs dates renseignées.

4. **Pour chaque mouvement**, une ligne est créée dans le rapport (pas de regroupement).

## 🔄 Personnalisations possibles

- Ajouter des filtres (par produit, par fabricant)
- Inclure les mouvements internes
- Ajouter des totaux en bas du rapport
- Générer automatiquement chaque mois (cron)
