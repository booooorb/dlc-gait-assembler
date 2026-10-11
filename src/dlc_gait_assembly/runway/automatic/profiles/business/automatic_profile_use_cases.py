"""Coordinate profile selection and persisted configuration changes without running stages."""

from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_ports import AutomaticProfileRepositoryPort


class AutomaticProfileUseCases:
    def __init__(self, repository: AutomaticProfileRepositoryPort, manual_assets, asset_reader):
        self.repository = repository
        self.manual_assets = manual_assets
        self.asset_reader = asset_reader

    def list_profiles(self):
        return self.repository.list_profiles()

    def load(self, profile_id):
        return self.repository.load(profile_id)

    def save(self, *args, **settings):
        return self.repository.save(*args, **settings)

    def duplicate(self, profile_id, name):
        source = self.repository.load(profile_id)
        return self.repository.save(
            name,
            source.processing_manifest,
            source.calibration_map,
            source.deeplabcut_models,
            analysis_manifest=source.analysis_manifest,
            knee_manifest=source.knee_manifest,
            gait_analysis_enabled=source.gait_analysis_enabled,
            knee_correction_enabled=source.knee_correction_enabled,
            allow_incomplete=True,
        )

    def delete(self, profile_id):
        return self.repository.delete(profile_id)

    def create_from_manual(self, name, snapshot):
        with self.manual_assets.materialize(snapshot) as assets:
            profile = self.repository.save(
                name,
                assets.processing_manifest,
                assets.calibration_map,
                {},
                analysis_manifest=assets.analysis_manifest,
                knee_manifest=assets.knee_manifest,
                gait_analysis_enabled=assets.analysis_manifest is not None,
                knee_correction_enabled=assets.knee_manifest is not None,
                allow_incomplete=True,
            )
            return (profile, assets.present_names())

    def processing_regions(self, path):
        return self.asset_reader.regions(path)

    def inspect_gait_settings(self, path):
        return self.asset_reader.gait_settings(path)

    def inspect_knee_settings(self, path):
        return self.asset_reader.knee_settings(path)

    def missing_requirements(self, profile):
        from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_validation import (
            profile_missing_requirements,
        )

        valid_manifest = True
        try:
            regions = (
                self.processing_regions(profile.processing_manifest) if profile.processing_manifest is not None else ()
            )
        except (OSError, ValueError):
            regions = ()
            valid_manifest = False
        return profile_missing_requirements(profile, regions, valid_manifest)
