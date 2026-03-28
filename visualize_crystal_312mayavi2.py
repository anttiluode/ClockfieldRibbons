# visualize_crystal_312mayavi.py
import numpy as np
from scipy.fft import fftn, ifftn, fftfreq
import matplotlib.pyplot as plt
import time

try:
    from mayavi import mlab
except ImportError:
    print("Warning: Mayavi is not installed. 3D visualization will fail.")
    print("Install via: pip install mayavi PyQt5")

class ClockfieldStaticCrystal:
    def __init__(self, N=48, L=20.0, tau=9.5):
        self.N = N
        self.L = L
        self.dx = L / N
        self.x = np.linspace(-L/2, L/2, N, endpoint=False)
        self.X, self.Y, self.Z = np.meshgrid(self.x, self.x, self.x, indexing='ij')

        # --- THE ETERNAL CRYSTAL PARAMETERS ---
        self.tau = tau            
        self.mu2 = 2.2
        self.lambda_ = 1.1
        self.Xi = 4.0 / np.pi     
        
        self.gamma_base = 0.0001
        self.gamma_born_strength = 0.015   

        self.phi = np.zeros((N, N, N), dtype=complex)
        self.t_im = 0.0
        self.step = 0

        self.energy_history = []
        self.beta_history = []
        self.sep_history = []

        freqs = fftfreq(N, self.dx) * 2 * np.pi
        kx, ky, kz = np.meshgrid(freqs, freqs, freqs, indexing='ij')
        self.K2 = kx**2 + ky**2 + kz**2

        # Initialize the Braided Worldline
        self.initialize_double_helix(R0=2.5, twists=1.0)

    def initialize_double_helix(self, R0=2.5, twists=1.0):
        """
        Initializes a Temporal Double Helix (The True Block Universe Fermion).
        Z represents Time. The two strings twist around each other,
        creating an eternal braided worldline. 
        """
        self.phi[:] = 0.0 + 0j
        core_thickness = 1.5

        k = (2.0 * np.pi * twists) / self.L

        # --- HELIX 1: Vortex ---
        x1 = R0 * np.cos(k * self.Z)
        y1 = R0 * np.sin(k * self.Z)
        
        r1_sq = (self.X - x1)**2 + (self.Y - y1)**2
        theta1 = np.arctan2(self.Y - y1, self.X - x1)
        
        amp1 = np.sqrt(r1_sq) / np.sqrt(r1_sq + core_thickness**2)
        phi1 = amp1 * np.exp(1j * theta1)

        # --- HELIX 2: Anti-Vortex ---
        x2 = R0 * np.cos(k * self.Z + np.pi)
        y2 = R0 * np.sin(k * self.Z + np.pi)
        
        r2_sq = (self.X - x2)**2 + (self.Y - y2)**2
        theta2 = -np.arctan2(self.Y - y2, self.X - x2) 
        
        amp2 = np.sqrt(r2_sq) / np.sqrt(r2_sq + core_thickness**2)
        phi2 = amp2 * np.exp(1j * theta2)

        self.phi = phi1 * phi2
        
        self.target_dist = R0 * 2
        print(f"Static Crystal Init | τ={self.tau} | Topology: Double Helix (Braided Worldline)")

    def laplacian(self, f):
        return ifftn(-self.K2 * fftn(f))

    def relax_step(self, dtau=0.01):
        """One step of imaginary-time relaxation."""
        beta = np.abs(self.phi)**2
        g = 1.0 / (1.0 + self.tau * beta)**2
        
        lap = self.laplacian(self.phi)
        
        V_prime = (self.mu2 - 2.0 * self.lambda_ * beta) * self.phi
        force = (g**2) * (lap + V_prime)
        
        gamma_born = self.gamma_born_strength * (beta / self.Xi)**2
        force -= (self.gamma_base + gamma_born) * self.phi
        
        self.phi += dtau * force
        
        self.t_im += dtau
        self.step += 1

        if self.step % 20 == 0:
            self._record_diagnostics(beta)

    def _record_diagnostics(self, beta):
        grad_phi = np.gradient(self.phi, self.dx)
        grad_sq_sum = np.sum([np.abs(axis_g)**2 for axis_g in grad_phi])
        v_beta = np.sum(self.mu2 * beta - self.lambda_ * beta**2)
        
        total_energy = np.real(np.sum(grad_sq_sum + v_beta)) * (self.dx**3)

        mid_z = self.N // 2
        plane_beta = beta[:, :, mid_z]
        left_half = plane_beta[:self.N//2, :]
        right_half = plane_beta[self.N//2:, :]
        
        idx_l = np.unravel_index(np.argmax(left_half), left_half.shape)
        idx_r = np.unravel_index(np.argmax(right_half), right_half.shape)
        idx_r = (idx_r[0] + self.N//2, idx_r[1])
        
        dx_val = abs(idx_l[0] - idx_r[0])
        dy_val = abs(idx_l[1] - idx_r[1])
        dx_val = min(dx_val, self.N - dx_val)
        dy_val = min(dy_val, self.N - dy_val)
        dist = np.sqrt(dx_val**2 + dy_val**2) * self.dx

        self.energy_history.append(total_energy)
        self.beta_history.append(float(np.max(beta)))
        self.sep_history.append(float(dist))

    def run_relaxation(self, max_steps=6000):
        print("Starting imaginary-time relaxation -> testing worldline stability...")
        start = time.time()
        for i in range(max_steps):
            self.relax_step()
            if i % 500 == 0 and len(self.energy_history) > 0:
                E = self.energy_history[-1]
                b = self.beta_history[-1]
                s = self.sep_history[-1]
                print(f"Step {i:5d} | imag-time {self.t_im:.2f} | E={E:.3e} | max_β={b:.4f} | helix_width={s:.2f}")
                
        print(f"\nRelaxation finished in {time.time()-start:.1f} s.")
        print(f"Final max_β = {self.beta_history[-1]:.4f}")

    def plot_temporal_blur(self):
        """
        Visualizes the specific physical insight:
        Projects the 4D braided worldline (Z=Time) down onto a 3D observer's
        XY plane, effectively simulating a temporal integration window.
        This renders the 'quantum orbital' smear caused by observing a time-extended object.
        """
        beta = np.abs(self.phi)**2
        
        # Integrate (mean) across the Z (Time) axis to simulate temporal blurring
        temporal_blur = np.mean(beta, axis=2)
        
        plt.figure(figsize=(8, 6), facecolor='#0d1117')
        ax = plt.gca()
        ax.set_facecolor('#0d1117')
        
        # Plot the blurred projection
        im = plt.imshow(temporal_blur, cmap='plasma', origin='lower', extent=[-self.L/2, self.L/2, -self.L/2, self.L/2])
        
        plt.colorbar(im, label='Time-Averaged Energy Density (β)')
        plt.title('3D Observer View: Temporal Blur of 4D Braid', color='white', pad=15)
        plt.xlabel('X Space', color='white')
        plt.ylabel('Y Space', color='white')
        ax.tick_params(colors='white')
        
        plt.tight_layout()
        plt.show()

    def visualize_mayavi(self):
        """
        Renders the highly detailed 3D isosurface using Mayavi.
        """
        print("Launching Mayavi 3D Crystal Viewer...")
        beta = np.abs(self.phi)**2
        max_b = float(np.max(beta))
        
        if max_b < 0.01:
            print("The structure melted completely. Nothing to show.")
            return

        outer_shell = max_b * 0.30  
        gate_shell  = max_b * 0.60  
        inner_core  = max_b * 0.85  
        
        mlab.figure(bgcolor=(0.05, 0.05, 0.05), size=(800, 800))
        
        src = mlab.pipeline.scalar_field(beta)
        vol = mlab.pipeline.iso_surface(
            src, 
            contours=[outer_shell, gate_shell, inner_core],
            opacity=0.4, 
            colormap='plasma'
        )
        
        mlab.outline()
        mlab.axes(xlabel='X', ylabel='Y', zlabel='Z (Time)')
        mlab.title(f'Temporal Double Helix (max_β={max_b:.3f})')
        mlab.show()

if __name__ == "__main__":
    sim = ClockfieldStaticCrystal(N=48, L=20.0, tau=9.5)
    sim.run_relaxation(max_steps=6000)
    
    # 1. Plot the physical reality of the observer (The Blur)
    sim.plot_temporal_blur()
    
    # 2. Plot the 4D Block Universe View
    sim.visualize_mayavi()