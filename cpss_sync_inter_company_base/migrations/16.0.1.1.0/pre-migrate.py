import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Supprime les colonnes et contraintes FK liées aux champs supprimés
    dans la version 16.0.1.1.0 :
      - utilisateur_intersocietes_id     (cpss_sync_config)
      - notifier_erreurs_sync            (cpss_sync_config)
      - utilisateurs_notification_erreurs (cpss_sync_config, table M2M)
      - sync_utilisateur_intersocietes_id (res_company)
      - sync_notifier_erreurs            (res_company)
      - sync_utilisateurs_notification_ids (res_company, table M2M)
    """

    # ── cpss_sync_config ────────────────────────────────────────────────────

    # 1. Supprimer FK et colonne utilisateur_intersocietes_id
    cr.execute("""
        ALTER TABLE cpss_sync_config
            DROP CONSTRAINT IF EXISTS cpss_sync_config_utilisateur_intersocietes_id_fkey
    """)
    cr.execute("""
        ALTER TABLE cpss_sync_config
            DROP COLUMN IF EXISTS utilisateur_intersocietes_id
    """)
    _logger.info("Migration: cpss_sync_config.utilisateur_intersocietes_id supprimé")

    # 2. Supprimer colonne notifier_erreurs_sync (boolean, pas de FK)
    cr.execute("""
        ALTER TABLE cpss_sync_config
            DROP COLUMN IF EXISTS notifier_erreurs_sync
    """)
    _logger.info("Migration: cpss_sync_config.notifier_erreurs_sync supprimé")

    # 3. Supprimer la table relation M2M pour utilisateurs_notification_erreurs
    #    (table générée automatiquement par Odoo)
    cr.execute("""
        DROP TABLE IF EXISTS cpss_sync_config_res_users_rel
    """)
    # Autre nom possible si Odoo a utilisé une convention différente
    cr.execute("""
        DROP TABLE IF EXISTS cpss_sync_config_utilisateurs_notification_rel
    """)
    _logger.info("Migration: table M2M notification cpss_sync_config supprimée")

    # ── res_company ──────────────────────────────────────────────────────────

    # 4. Supprimer FK et colonne sync_utilisateur_intersocietes_id
    cr.execute("""
        ALTER TABLE res_company
            DROP CONSTRAINT IF EXISTS res_company_sync_utilisateur_intersocietes_id_fkey
    """)
    cr.execute("""
        ALTER TABLE res_company
            DROP COLUMN IF EXISTS sync_utilisateur_intersocietes_id
    """)
    _logger.info("Migration: res_company.sync_utilisateur_intersocietes_id supprimé")

    # 5. Supprimer colonne sync_notifier_erreurs (boolean)
    cr.execute("""
        ALTER TABLE res_company
            DROP COLUMN IF EXISTS sync_notifier_erreurs
    """)
    _logger.info("Migration: res_company.sync_notifier_erreurs supprimé")

    # 6. Supprimer la table M2M company_sync_notification_users_rel
    cr.execute("""
        DROP TABLE IF EXISTS company_sync_notification_users_rel
    """)
    _logger.info("Migration: table M2M notification res_company supprimée")

    _logger.info("Migration 16.0.1.1.0 terminée avec succès")
