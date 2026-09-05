"""
Central configuration loader for GraphSAGE models.
Loads parameters from configs/model_config.yaml
"""

import yaml
import os
from pathlib import Path


class Config:
    """Configuration manager for GraphSAGE models."""

    def __init__(self, config_path=None):
        if config_path is None:
            # Default to ../configs/model_config.yaml
            config_path = Path(__file__).parent.parent / "configs" / "model_config.yaml"

        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self):
        """Load YAML configuration file."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def get(self, key, default=None):
        """Get configuration value by key (supports dot notation)."""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    # Dataset properties
    @property
    def dataset_name(self):
        return self.get('dataset.name')

    @property
    def num_features(self):
        return self.get('dataset.num_features')

    @property
    def num_classes(self):
        return self.get('dataset.num_classes')

    # Base model properties
    @property
    def base_hidden_channels(self):
        return self.get('base_model.hidden_channels')

    @property
    def base_dropout(self):
        return self.get('base_model.dropout')

    @property
    def base_epochs(self):
        return self.get('base_model.epochs')

    @property
    def base_lr(self):
        return self.get('base_model.lr')

    # Reduced model properties
    @property
    def reduced_in_channels(self):
        return self.get('reduced_model.in_channels_reduced')

    @property
    def reduced_hidden_channels(self):
        return self.get('reduced_model.hidden_channels')

    @property
    def reduced_dropout(self):
        return self.get('reduced_model.dropout')

    @property
    def reduced_root_weight(self):
        return self.get('reduced_model.root_weight')

    @property
    def reduced_epochs(self):
        return self.get('reduced_model.epochs')

    @property
    def reduced_lr(self):
        return self.get('reduced_model.lr')

    # QAT model properties (uses active config)
    def _get_qat_config(self):
        """Get active QAT configuration."""
        active = self.get('active_qat_config', 'qat_model')
        return self.config.get(active, self.config.get('qat_model', {}))

    @property
    def qat_in_channels(self):
        return self._get_qat_config().get('in_channels_reduced')

    @property
    def qat_hidden_channels(self):
        return self._get_qat_config().get('hidden_channels')

    @property
    def qat_dropout(self):
        return self._get_qat_config().get('dropout')

    @property
    def qat_root_weight(self):
        return self._get_qat_config().get('root_weight')

    @property
    def qat_epochs(self):
        return self._get_qat_config().get('epochs')

    @property
    def qat_lr(self):
        return self._get_qat_config().get('lr')

    @property
    def qat_calibration_batches(self):
        return self._get_qat_config().get('calibration_batches')

    @property
    def qat_num_bits_acts(self):
        return self._get_qat_config().get('num_bits_acts')

    @property
    def qat_num_bits_weights(self):
        return self._get_qat_config().get('num_bits_weights')

    # Quantization properties
    @property
    def quant_num_bits(self):
        return self.get('quantization.num_bits')

    @property
    def quant_test_nodes(self):
        return self.get('quantization.test_subgraph_nodes')

    # Path properties
    @property
    def models_dir(self):
        return self.get('paths.models')

    @property
    def plots_dir(self):
        return self.get('paths.plots')

    def __repr__(self):
        return f"Config(path={self.config_path})"

    def print_summary(self):
        """Print configuration summary."""
        print("=" * 60)
        print("Configuration Summary")
        print("=" * 60)
        print(f"\nDataset: {self.dataset_name}")
        print(f"  Features: {self.num_features}")
        print(f"  Classes: {self.num_classes}")

        print(f"\nBase Model:")
        print(f"  Hidden: {self.base_hidden_channels}")
        print(f"  Epochs: {self.base_epochs}, LR: {self.base_lr}")

        print(f"\nReduced Model:")
        print(f"  Architecture: {self.reduced_in_channels} → {self.reduced_hidden_channels} → {self.num_classes}")
        print(f"  Root weight: {self.reduced_root_weight}")
        print(f"  Epochs: {self.reduced_epochs}, LR: {self.reduced_lr}")

        print(f"\nQAT Model (active: {self.get('active_qat_config')}):")
        print(f"  Architecture: {self.qat_in_channels} → {self.qat_hidden_channels} → {self.num_classes}")
        print(f"  Quantization: INT{self.qat_num_bits_weights} weights, INT{self.qat_num_bits_acts} acts")
        print(f"  Epochs: {self.qat_epochs}, LR: {self.qat_lr}")
        print(f"  Calibration batches: {self.qat_calibration_batches}")
        print("=" * 60)


# Global config instance
_config = None


def get_config(config_path=None):
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = Config(config_path)
    return _config


# Convenience function for backwards compatibility
def load_config(config_path=None):
    """Load configuration (backwards compatible)."""
    return get_config(config_path)


if __name__ == '__main__':
    # Test the config
    config = get_config()
    config.print_summary()
