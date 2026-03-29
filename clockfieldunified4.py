import torch
import torch.nn.functional as F
import numpy as np
from ursina import *
from panda3d.core import Texture

# ==========================================
# 1. GPU PHYSICS ENGINE (Complex Clockfield)
# ==========================================
class GPUClockfield:
    def __init__(self, N=96, dt=0.04, device=None):
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.N = N
        self.dt = dt
        self.tau = 9.5
        self.mu2 = 1.0      # quadratic potential coefficient
        self.lambd = 1.0    # quartic coefficient

        # Complex field as two real tensors
        self.phi_r = torch.zeros((1,1,N,N,N), device=self.device)
        self.phi_i = torch.zeros_like(self.phi_r)
        self.phi_r_old = torch.zeros_like(self.phi_r)
        self.phi_i_old = torch.zeros_like(self.phi_i)

        # Initial condition: Gaussian pulse with zero phase
        x = torch.linspace(-1, 1, N, device=self.device)
        X, Y, Z = torch.meshgrid(x, x, x, indexing='ij')
        r2 = X**2 + Y**2 + Z**2
        init = 2.5 * torch.exp(-r2 / 0.4)

        self.phi_r[0,0] = init
        self.phi_i[0,0] = 0.0
        self.phi_r_old[0,0] = init.clone()
        self.phi_i_old[0,0] = 0.0

        # Laplacian kernel (7-point stencil)
        kernel = torch.zeros((1,1,3,3,3), device=self.device)
        kernel[0,0,1,1,1] = -6
        kernel[0,0,0,1,1] = 1
        kernel[0,0,2,1,1] = 1
        kernel[0,0,1,0,1] = 1
        kernel[0,0,1,2,1] = 1
        kernel[0,0,1,1,0] = 1
        kernel[0,0,1,1,2] = 1
        self.kernel = kernel

    def laplacian(self, f):
        return F.conv3d(f, self.kernel, padding=1)

    def step(self, substeps=4):
        dt = self.dt
        for _ in range(substeps):
            # Compute |phi|^2
            beta = self.phi_r**2 + self.phi_i**2

            # Proper-time factor
            gamma = 1.0 / (1.0 + self.tau * beta + 1e-8)**2

            # Laplacian of real and imag parts
            lap_r = self.laplacian(self.phi_r)
            lap_i = self.laplacian(self.phi_i)

            # Potential derivative: V' = (mu^2 - 2 lambda |phi|^2) phi
            Vp_r = (self.mu2 - 2.0 * self.lambd * beta) * self.phi_r
            Vp_i = (self.mu2 - 2.0 * self.lambd * beta) * self.phi_i

            # Force = gamma^2 * (Laplacian - V')
            force_r = gamma**2 * (lap_r - Vp_r)
            force_i = gamma**2 * (lap_i - Vp_i)

            # Biharmonic stabilization
            biharm_r = self.laplacian(lap_r)
            biharm_i = self.laplacian(lap_i)
            force_r -= 0.01 * biharm_r
            force_i -= 0.01 * biharm_i

            # Verlet integration
            vel_r = self.phi_r - self.phi_r_old
            vel_i = self.phi_i - self.phi_i_old

            new_r = self.phi_r + (1.0 - 0.003 * dt) * vel_r + dt*dt * force_r
            new_i = self.phi_i + (1.0 - 0.003 * dt) * vel_i + dt*dt * force_i

            self.phi_r_old = self.phi_r
            self.phi_i_old = self.phi_i
            self.phi_r = new_r
            self.phi_i = new_i

    def get_field_data(self):
        """Return amplitude and phase as numpy arrays."""
        beta = (self.phi_r**2 + self.phi_i**2).detach().cpu().numpy()[0,0]
        phase = torch.atan2(self.phi_i, self.phi_r).detach().cpu().numpy()[0,0]
        return beta, phase

    def get_color_texture(self):
        """Compute a 3D RGB texture where hue encodes phase and brightness encodes amplitude."""
        beta, phase = self.get_field_data()

        # Normalize amplitude to [0,1] for brightness
        beta_max = beta.max()
        if beta_max > 1e-8:
            brightness = np.clip(beta / beta_max, 0, 1)
        else:
            brightness = np.zeros_like(beta)

        # Map phase from [-π, π] to [0, 1]
        hue = (phase + np.pi) / (2 * np.pi)
        hue = np.clip(hue, 0, 1)

        # Convert HSV to RGB (fast vectorized)
        # hsv: hue, saturation=1, value=brightness
        # Using formula from https://en.wikipedia.org/wiki/HSL_and_HSV#HSV_to_RGB
        h = hue * 6.0
        i = np.floor(h).astype(int)
        f = h - i
        p = brightness * (1.0 - 1.0)  # saturation=1 -> p=0
        q = brightness * (1.0 - f)
        t = brightness * f
        r = np.zeros_like(hue)
        g = np.zeros_like(hue)
        b = np.zeros_like(hue)

        # Cases for each sector
        mask0 = i == 0
        r[mask0] = brightness[mask0]
        g[mask0] = t[mask0]
        b[mask0] = p[mask0]

        mask1 = i == 1
        r[mask1] = q[mask1]
        g[mask1] = brightness[mask1]
        b[mask1] = p[mask1]

        mask2 = i == 2
        r[mask2] = p[mask2]
        g[mask2] = brightness[mask2]
        b[mask2] = t[mask2]

        mask3 = i == 3
        r[mask3] = p[mask3]
        g[mask3] = q[mask3]
        b[mask3] = brightness[mask3]

        mask4 = i == 4
        r[mask4] = t[mask4]
        g[mask4] = p[mask4]
        b[mask4] = brightness[mask4]

        mask5 = i == 5
        r[mask5] = brightness[mask5]
        g[mask5] = p[mask5]
        b[mask5] = q[mask5]

        # Stack into RGB array of shape (N,N,N,3)
        rgb = np.stack([r, g, b], axis=-1).astype(np.float32)

        # Also return alpha based on brightness (optional)
        alpha = brightness.astype(np.float32)
        return rgb, alpha


# ==========================================
# 2. URSINA RENDERER (Raymarching with RGB volume)
# ==========================================
app = Ursina()
window.color = color.black
window.title = "Clockfield GPU - Phase Visualization"

N = 96
sim = GPUClockfield(N=N)

# Create a 3D RGB texture (format F_rgb32)
tex = Texture()
tex.setup3dTexture(N, N, N, Texture.T_unsigned_byte, Texture.F_rgb)

# --- Raymarching Shader (now samples RGB volume) ---
raymarch_shader = Shader(
    language=Shader.GLSL,
    vertex='''
    #version 140
    in vec4 p3d_Vertex;
    uniform mat4 p3d_ModelViewProjectionMatrix;
    uniform mat4 p3d_ModelMatrixInverse;
    uniform mat4 p3d_ViewMatrixInverse;

    out vec3 local_pos;
    out vec3 cam_local_pos;

    void main() {
        local_pos = p3d_Vertex.xyz; 
        vec3 cam_world = p3d_ViewMatrixInverse[3].xyz;
        cam_local_pos = (p3d_ModelMatrixInverse * vec4(cam_world, 1.0)).xyz;
        gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    }
    ''',

    fragment='''
    #version 140
    uniform sampler3D volume_tex;
    in vec3 local_pos;
    in vec3 cam_local_pos;
    out vec4 fragColor;

    void main() {
        vec3 ray_dir = normalize(local_pos - cam_local_pos);
        vec3 p = local_pos; 
        vec4 accum = vec4(0.0);
        float step_size = 0.02; 
        
        for(int i = 0; i < 100; i++) {
            vec3 tc = p * 0.5 + 0.5; 
            if(any(lessThan(tc, vec3(0.0))) || any(greaterThan(tc, vec3(1.0)))) break;
            
            vec3 rgb = texture(volume_tex, tc).rgb;
            float intensity = max(rgb.r, max(rgb.g, rgb.b)); // brightness as alpha proxy
            
            if (intensity > 0.02) {
                float alpha = intensity * 0.2;  // transparency based on brightness
                accum += vec4(rgb * alpha, alpha) * (1.0 - accum.a);
                if (accum.a > 0.98) break;
            }
            p += ray_dir * step_size;
        }
        fragColor = accum;
    }
    '''
)

# Cube that hosts the volume texture
volume = Entity(
    model='cube',
    scale=20,
    shader=raymarch_shader,
    transparent=True
)
volume.set_shader_input("volume_tex", tex)

EditorCamera()
Text("WASD + Right Click | Phase: Hue | Amplitude: Brightness", y=0.45, background=True)

def update():
    sim.step(3)               # evolve the field
    rgb, _ = sim.get_color_texture()

    # Convert RGB float array to uint8 and upload
    rgb_uint8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    tex.setRamImage(rgb_uint8.tobytes())

app.run()