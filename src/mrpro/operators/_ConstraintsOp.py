"""Operator enforcing constraints by variable transformations."""

# Copyright 2024 Physikalisch-Technische Bundesanstalt
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

from collections.abc import Sequence

import torch
import torch.nn.functional as F  # noqa: N812

from mrpro.operators import Operator


class ConstraintsOp(Operator[*tuple[torch.Tensor, ...], tuple[torch.Tensor, ...]]):
    """Transformation to map real-valued tensors to certain ranges."""

    def __init__(
        self,
        bounds: Sequence[tuple[float | None, float | None]],
        beta_sigmoid: float = 1.0,
        beta_softplus: float = 1.0,
    ) -> None:
        super().__init__()

        if beta_sigmoid <= 0:
            raise ValueError(f'parameter beta_sigmoid must be greater than zero; given {beta_sigmoid}')
        if beta_softplus <= 0:
            raise ValueError(f'parameter beta_softplus must be greater than zero; given {beta_softplus}')

        self.beta_sigmoid = beta_sigmoid
        self.beta_softplus = beta_softplus

        self.lower_bounds = [bound[0] for bound in bounds]
        self.upper_bounds = [bound[1] for bound in bounds]

        for lb, ub in bounds:
            if lb is not None and ub is not None:
                if torch.isnan(torch.tensor(lb)) or torch.isnan(torch.tensor(ub)):
                    raise ValueError(' "nan" is not a valid lower or upper bound;' f'\nbound tuple {lb, ub} is invalid')

                if lb >= ub:
                    raise ValueError(
                        'bounds should be ( (a1,b1), (a2,b2), ...) with ai < bi if neither ai or bi is None;'
                        f'\nbound tuple {lb, ub} is invalid',
                    )

    @staticmethod
    def sigmoid(x: torch.Tensor, beta: float = 1.0) -> torch.Tensor:
        """Constraint x to be in the range given by 'bounds'."""
        return F.sigmoid(beta * x)

    @staticmethod
    def sigmoid_inverse(x: torch.Tensor, beta: float = 1.0) -> torch.Tensor:
        """Constraint x to be in the range given by 'bounds'."""
        return torch.logit(x) / beta

    @staticmethod
    def softplus(x: torch.Tensor, beta: float = 1.0) -> torch.Tensor:
        """Constrain x to be in (bound,infty)."""
        return -(1 / beta) * torch.nn.functional.logsigmoid(-beta * x)

    @staticmethod
    def softplus_inverse(x: torch.Tensor, beta: float = 1.0) -> torch.Tensor:
        """Inverse of 'softplus_transformation."""
        return beta * x + torch.log(-torch.expm1(-beta * x))

    def forward(self, *x: torch.Tensor) -> tuple[torch.Tensor, ...]:
        """Transform tensors to chosen range.

        Parameters
        ----------
        x
            tensors to be transformed

        Returns
        -------
            tensors transformed to the range defined by the chosen bounds
        """
        x_constrained = []
        for item, lb, ub in zip(x, self.lower_bounds, self.upper_bounds, strict=False):
            # distinguish cases
            if (lb is not None and not torch.isneginf(torch.tensor(lb))) and (
                ub is not None and not torch.isposinf(torch.tensor(ub))
            ):
                # case (a,b) with a<b and a,b \in R
                x_constrained.append(lb + (ub - lb) * self.sigmoid(item, beta=self.beta_sigmoid))

            elif lb is not None and (ub is None or torch.isposinf(torch.tensor(ub))):
                # case (a,None); corresponds to (a, \infty)
                x_constrained.append(lb + self.softplus(item, beta=self.beta_softplus))

            elif (lb is None or torch.isneginf(torch.tensor(lb))) and ub is not None:
                # case (None,b); corresponds to (-\infty, b)
                x_constrained.append(ub - self.softplus(-item, beta=self.beta_softplus))
            elif (lb is None or torch.isneginf(torch.tensor(lb))) and (ub is None or torch.isposinf(torch.tensor(ub))):
                # case (None,None); corresponds to (-\infty, \infty), i.e. no transformation
                x_constrained.append(item)

        # if there are more inputs than bounds, pass on the remaining inputs without transformation
        x_constrained.extend(x[len(x_constrained) :])
        return tuple(x_constrained)

    def inverse(self, *x_constrained: torch.Tensor) -> tuple[torch.Tensor, ...]:
        """Reverses the variable transformation.

        Parameters
        ----------
        x_constrained
            transformed tensors with values in the range defined by the bounds

        Returns
        -------
            tensors in the domain with no bounds
        """
        # iterate over the tensors and constrain them if necessary according to the
        # chosen bounds
        x = []
        for item, lb, ub in zip(x_constrained, self.lower_bounds, self.upper_bounds, strict=False):
            # distinguish cases
            if (lb is not None and not torch.isneginf(torch.tensor(lb))) and (
                ub is not None and not torch.isposinf(torch.tensor(ub))
            ):
                # case (a,b) with a<b and a,b \in R
                x.append(self.sigmoid_inverse((item - lb) / (ub - lb), beta=self.beta_sigmoid))

            elif lb is not None and (ub is None or torch.isposinf(torch.tensor(ub))):
                # case (a,None); corresponds to (a, \infty)
                x.append(self.softplus_inverse(item - lb, beta=self.beta_softplus))

            elif (lb is None or torch.isneginf(torch.tensor(lb))) and ub is not None:
                # case (None,b); corresponds to (-\infty, b)
                x.append(-self.softplus_inverse(-(item - ub), beta=self.beta_softplus))
            elif (lb is None or torch.isneginf(torch.tensor(lb))) and (ub is None or torch.isposinf(torch.tensor(ub))):
                # case (None,None); corresponds to (-\infty, \infty), i.e. no transformation
                x.append(item)

        # if there are more inputs than bounds, pass on the remaining inputs without transformation
        x.extend(x_constrained[len(x) :])
        return tuple(x)