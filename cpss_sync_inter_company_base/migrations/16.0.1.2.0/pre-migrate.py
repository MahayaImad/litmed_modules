import logging

_logger = logging.getLogger(__name__)

# Modèles retirés du code en 16.0.1.2.0 (jamais utilisés).
MODELES_SUPPRIMES = (
    'cpss.sync.history',
    'cpss.sync.mixin',
)


def migrate(cr, version):
    """Supprime les métadonnées des modèles retirés en 16.0.1.2.0.

    Odoo ne sait pas nettoyer seul un modèle disparu du code lorsque celui-ci
    porte des champs Selection : en fin de mise à jour, `_process_end` supprime
    les `ir.model.fields` orphelins et `_process_ondelete` résout
    `self.env[selection.field_id.model]` pour appliquer la politique `ondelete`
    de chaque valeur. Le modèle n'étant plus dans le registre, la mise à jour
    échoue sur `KeyError: <modèle>`.

    On supprime donc ces métadonnées avant que le module ne soit chargé.
    """
    if not version:
        return

    for modele in MODELES_SUPPRIMES:
        _supprimer_metadonnees_modele(cr, modele)


def _supprimer_metadonnees_modele(cr, modele):
    """Supprime toute trace d'un modèle en base (idempotent)."""
    cr.execute("SELECT id FROM ir_model WHERE model = %s", (modele,))
    if not cr.fetchone():
        _logger.info("Modèle %s déjà absent, rien à nettoyer", modele)
        return

    # 1. ir.model.data des valeurs de sélection, puis les valeurs elles-mêmes.
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE model = 'ir.model.fields.selection'
           AND res_id IN (
               SELECT s.id
                 FROM ir_model_fields_selection s
                 JOIN ir_model_fields f ON f.id = s.field_id
                WHERE f.model = %s)
    """, (modele,))
    cr.execute("""
        DELETE FROM ir_model_fields_selection
         WHERE field_id IN (SELECT id FROM ir_model_fields WHERE model = %s)
    """, (modele,))

    # 2. Propriétés et ir.model.data des champs, puis les champs.
    cr.execute("""
        DELETE FROM ir_property
         WHERE fields_id IN (SELECT id FROM ir_model_fields WHERE model = %s)
    """, (modele,))
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE model = 'ir.model.fields'
           AND res_id IN (SELECT id FROM ir_model_fields WHERE model = %s)
    """, (modele,))
    cr.execute("DELETE FROM ir_model_fields WHERE model = %s", (modele,))

    # 3. Droits d'accès et règles d'enregistrement.
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE model = 'ir.model.access'
           AND res_id IN (
               SELECT a.id FROM ir_model_access a
                 JOIN ir_model m ON m.id = a.model_id
                WHERE m.model = %s)
    """, (modele,))
    cr.execute("""
        DELETE FROM ir_model_access
         WHERE model_id IN (SELECT id FROM ir_model WHERE model = %s)
    """, (modele,))
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE model = 'ir.rule'
           AND res_id IN (
               SELECT r.id FROM ir_rule r
                 JOIN ir_model m ON m.id = r.model_id
                WHERE m.model = %s)
    """, (modele,))
    cr.execute("""
        DELETE FROM ir_rule
         WHERE model_id IN (SELECT id FROM ir_model WHERE model = %s)
    """, (modele,))

    # 4. Contraintes et relations déclarées pour ce modèle.
    cr.execute("""
        DELETE FROM ir_model_constraint
         WHERE model IN (SELECT id FROM ir_model WHERE model = %s)
    """, (modele,))
    cr.execute("""
        DELETE FROM ir_model_relation
         WHERE model IN (SELECT id FROM ir_model WHERE model = %s)
    """, (modele,))

    # 5. Le modèle lui-même, son ir.model.data et sa table.
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE model = 'ir.model'
           AND res_id IN (SELECT id FROM ir_model WHERE model = %s)
    """, (modele,))
    cr.execute("DELETE FROM ir_model WHERE model = %s", (modele,))
    cr.execute('DROP TABLE IF EXISTS "%s" CASCADE' % modele.replace('.', '_'))

    _logger.info("Métadonnées du modèle %s supprimées", modele)
