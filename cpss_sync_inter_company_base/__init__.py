import logging

from . import models

_logger = logging.getLogger(__name__)


def pre_init_hook(cr):
    """Supprime les artefacts d'une ancienne version du module.

    Ce hook n'est exécuté qu'à l'installation. Les bases déjà installées sont
    traitées par les scripts de `migrations/`.
    """
    _cleanup_old_columns(cr)


def _cleanup_old_columns(cr):
    """Supprime les colonnes et contraintes obsolètes (idempotent)."""

    ops = [
        # cpss_sync_config — utilisateur technique
        "ALTER TABLE cpss_sync_config DROP CONSTRAINT IF EXISTS cpss_sync_config_utilisateur_intersocietes_id_fkey",
        "ALTER TABLE cpss_sync_config DROP COLUMN IF EXISTS utilisateur_intersocietes_id",
        # cpss_sync_config — notifications
        "ALTER TABLE cpss_sync_config DROP COLUMN IF EXISTS notifier_erreurs_sync",
        "DROP TABLE IF EXISTS cpss_sync_config_res_users_rel",
        "DROP TABLE IF EXISTS cpss_sync_config_utilisateurs_notification_rel",
        # res_company — utilisateur technique
        "ALTER TABLE res_company DROP CONSTRAINT IF EXISTS res_company_sync_utilisateur_intersocietes_id_fkey",
        "ALTER TABLE res_company DROP COLUMN IF EXISTS sync_utilisateur_intersocietes_id",
        # res_company — notifications
        "ALTER TABLE res_company DROP COLUMN IF EXISTS sync_notifier_erreurs",
        "DROP TABLE IF EXISTS company_sync_notification_users_rel",
        # res_company — champs sync devenus inutiles (config globale via cpss.sync.config)
        "ALTER TABLE res_company DROP CONSTRAINT IF EXISTS res_company_sync_societe_operationnelle_id_fkey",
        "ALTER TABLE res_company DROP COLUMN IF EXISTS sync_societe_operationnelle_id",
        "ALTER TABLE res_company DROP CONSTRAINT IF EXISTS res_company_sync_societe_cible_id_fkey",
        "ALTER TABLE res_company DROP COLUMN IF EXISTS sync_societe_cible_id",
        "ALTER TABLE res_company DROP CONSTRAINT IF EXISTS res_company_sync_journal_fiscal_defaut_id_fkey",
        "ALTER TABLE res_company DROP COLUMN IF EXISTS sync_journal_fiscal_defaut_id",
    ]

    for sql in ops:
        try:
            cr.execute("SAVEPOINT cpss_cleanup")
            cr.execute(sql)
            cr.execute("RELEASE SAVEPOINT cpss_cleanup")
        except Exception as error:
            cr.execute("ROLLBACK TO SAVEPOINT cpss_cleanup")
            _logger.warning("Cleanup SQL ignoré (%s) : %s", sql[:60], error)
