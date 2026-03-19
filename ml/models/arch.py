from __future__ import annotations

import torch
import torch.nn as nn


class MLPClassifier(nn.Module):
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        num_classes: int,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class Conv1dAutoencoder(nn.Module):
    def __init__(
        self,
        input_channels: int,
        hidden_dim: int,
        latent_dim: int,
    ) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv1d(input_channels, hidden_dim, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.Conv1d(hidden_dim, latent_dim, kernel_size=4, stride=2, padding=1),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.ConvTranspose1d(
                latent_dim, hidden_dim, kernel_size=4, stride=2, padding=1
            ),
            nn.ReLU(),
            nn.ConvTranspose1d(hidden_dim, input_channels, kernel_size=5, padding=2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))


class Conv1dClassifier(nn.Module):
    def __init__(
        self,
        input_channels: int,
        hidden_dim: int,
        num_classes: int,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(input_channels, hidden_dim, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.Conv1d(hidden_dim, hidden_dim, kernel_size=5, stride=2, padding=2),
            nn.ReLU(),
            nn.Conv1d(hidden_dim, hidden_dim, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(x))


class Model(nn.Module):
    def __init__(
        self,
        *,
        model_type: str = "mlp_classifier",
        input_dim: int | None = None,
        hidden_dim: int = 64,
        num_classes: int | None = None,
        dropout: float = 0.1,
        input_channels: int | None = None,
        latent_dim: int = 32,
    ) -> None:
        super().__init__()
        self.model_type = model_type

        if model_type == "mlp_classifier":
            if input_dim is None or num_classes is None:
                raise ValueError("MLP classifier requires input_dim and num_classes")
            self.model = MLPClassifier(
                input_dim=input_dim,
                hidden_dim=hidden_dim,
                num_classes=num_classes,
                dropout=dropout,
            )
        elif model_type == "conv1d_autoencoder":
            if input_channels is None:
                raise ValueError("Conv1D autoencoder requires input_channels")
            self.model = Conv1dAutoencoder(
                input_channels=input_channels,
                hidden_dim=hidden_dim,
                latent_dim=latent_dim,
            )
        elif model_type == "conv1d_classifier":
            if input_channels is None or num_classes is None:
                raise ValueError("Conv1D classifier requires input_channels and num_classes")
            self.model = Conv1dClassifier(
                input_channels=input_channels,
                hidden_dim=hidden_dim,
                num_classes=num_classes,
                dropout=dropout,
            )
        else:
            raise ValueError(f"Unsupported model_type: {model_type}")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)
