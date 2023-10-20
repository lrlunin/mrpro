"""Tests for KTrajectory Calculator classes."""

# Copyright 2023 Physikalisch-Technische Bundesanstalt
#
# Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#       http://www.apache.org/licenses/LICENSE-2.0
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import numpy as np
import pytest
import torch

from mrpro.data.traj_calculators import KTrajectoryRpe
from mrpro.data.traj_calculators import KTrajectorySunflowerGoldenRpe
from tests.data.conftest import random_kheader


@pytest.fixture(scope='function')
def valid_rpe_kheader(monkeypatch, random_kheader):
    """KHeader with all necessary parameters for RPE trajectories."""
    # K-space dimensions
    nk0 = 200
    nk1 = 20
    nk2 = 10

    # List of k1 and k2 indices in the shape (other, k2, k1)
    k1 = torch.linspace(0, nk1 - 1, nk1, dtype=torch.int32)
    k2 = torch.linspace(0, nk2 - 1, nk2, dtype=torch.int32)
    idx_k1, idx_k2 = torch.meshgrid(k1, k2, indexing='xy')
    idx_k1 = torch.reshape(idx_k1, (1, nk2, nk1))
    idx_k2 = torch.reshape(idx_k2, (1, nk2, nk1))

    # Set parameters for RPE trajectory
    monkeypatch.setattr(random_kheader.acq_info, 'number_of_samples', torch.zeros_like(idx_k1) + nk0)
    monkeypatch.setattr(random_kheader.acq_info, 'center_sample', torch.zeros_like(idx_k1) + nk0 // 2)
    monkeypatch.setattr(random_kheader.acq_info.idx, 'k1', idx_k1)
    monkeypatch.setattr(random_kheader.acq_info.idx, 'k2', idx_k2)
    monkeypatch.setattr(random_kheader.encoding_limits.k1, 'center', int(nk1 // 2))
    monkeypatch.setattr(random_kheader.encoding_limits.k1, 'max', int(nk1 - 1))
    return random_kheader


def rpe_traj_shape(valid_rpe_kheader):
    """Expected shape of trajectory based on KHeader."""
    nk0 = valid_rpe_kheader.acq_info.number_of_samples[0, 0, 0]
    nk1 = valid_rpe_kheader.acq_info.idx.k1.shape[2]
    nk2 = valid_rpe_kheader.acq_info.idx.k1.shape[1]
    nother = 1
    return (torch.Size([nother, nk2, nk1, 1]), torch.Size([nother, nk2, nk1, 1]), torch.Size([nother, 1, 1, nk0]))


def test_KTrajectoryRpe_golden(valid_rpe_kheader):
    """Calculate RPE trajectory with golden angle."""
    ktrajectory = KTrajectoryRpe(angle=torch.pi * 0.618034)
    ktraj = ktrajectory(valid_rpe_kheader)
    valid_shape = rpe_traj_shape(valid_rpe_kheader)
    assert ktraj.kz.shape == valid_shape[0]
    assert ktraj.ky.shape == valid_shape[1]
    assert ktraj.kx.shape == valid_shape[2]


def test_KTrajectoryRpe_uniform(valid_rpe_kheader):
    """Calculate RPE trajectory with uniform angle."""
    num_rpe_lines = valid_rpe_kheader.acq_info.idx.k1.shape[1]
    ktrajectory1 = KTrajectoryRpe(angle=torch.pi / num_rpe_lines, shift_between_rpe_lines=torch.tensor([0]))
    ktraj1 = ktrajectory1(valid_rpe_kheader)
    # Calculate trajectory with half the angular gap such that every second line should be the same as above
    ktrajectory2 = KTrajectoryRpe(angle=torch.pi / (2 * num_rpe_lines), shift_between_rpe_lines=torch.tensor([0]))
    ktraj2 = ktrajectory2(valid_rpe_kheader)

    torch.testing.assert_close(ktraj1.kx[:, : num_rpe_lines // 2, :, :], ktraj2.kx[:, ::2, :, :])
    torch.testing.assert_close(ktraj1.ky[:, : num_rpe_lines // 2, :, :], ktraj2.ky[:, ::2, :, :])
    torch.testing.assert_close(ktraj1.kz[:, : num_rpe_lines // 2, :, :], ktraj2.kz[:, ::2, :, :])


def test_KTrajectoryRpe_shift(valid_rpe_kheader):
    """Evaluate radial shifts for RPE trajectory."""
    ktrajectory1 = KTrajectoryRpe(angle=torch.pi * 0.618034, shift_between_rpe_lines=torch.tensor([0.25]))
    ktraj1 = ktrajectory1(valid_rpe_kheader)
    ktrajectory2 = KTrajectoryRpe(
        angle=torch.pi * 0.618034, shift_between_rpe_lines=torch.tensor([0.25, 0.25, 0.25, 0.25])
    )
    ktraj2 = ktrajectory2(valid_rpe_kheader)
    torch.testing.assert_close(ktraj1.as_tensor(), ktraj2.as_tensor())


def test_KTrajectorySunflowerGoldenRpe(valid_rpe_kheader):
    """Calculate RPE Sunflower trajectory."""
    ktrajectory = KTrajectorySunflowerGoldenRpe(rad_us_factor=2)
    ktraj = ktrajectory(valid_rpe_kheader)
    assert ktraj.broadcasted_shape == np.broadcast_shapes(*rpe_traj_shape(valid_rpe_kheader))