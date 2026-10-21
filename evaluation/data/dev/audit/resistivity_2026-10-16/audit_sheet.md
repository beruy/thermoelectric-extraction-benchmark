# Resistivity audit of dev gold v1 (2026-10-16)

Scope: the `sigma` decisions only, in the 24 dev paragraphs below. Decide each paragraph from its
text and PROTOCOL.md §5.2. Do not open gold_records.csv, method outputs or score files while
auditing. The paragraphs are in shuffled order (seed 20261016).

## Rules to apply

* Resistivity becomes `sigma` (σ = 1/ρ) when its unit is explicit. Conductivity with an explicit unit is `sigma`.
* Not recorded: bounds and inequalities ("up to", "below", "as low as"), numbers damaged by PDF extraction
  (except an explicit ×10 notation), values without a unit, conductance, resistance (Ω without a length unit),
  ratios such as anisotropy ratios, activation energies, mobilities.
* Ranges: one record, lower bound and upper bound.
* Approximate values (~, ≈, about, around) are recorded in gold v1 elsewhere. Open question for D-numbers
  you meet: is "in the order of (about) X" a value? Write your answer in `notes`; we fix the rule before v1.1.

## How to fill `audit_sheet.csv`

* `sigma_decision`: `SIGMA` (at least one sigma record) or `NO_SIGMA`.
* `records`: one record per line or separated by ` | `, as `material ; value as written ; unit as written ; T as written`.
  Example: `Cu2Se ; 10 ; μΩ·m (resistivity) ; 323 K`. Write values as in the text; the conversion to S/m is done in code
  and shown to you for checking.
* `notes`: your reason, especially for NO_SIGMA.

You can also answer here in chat, paragraph by paragraph, by audit number.

## 1. D0085

Matched terms: resistiv, Omega/ohm

The electronic transport properties of CuCrS2 and CuCrSe2 have not been investigated in detail. A preliminary conductivity measurement on the crystals of CuCrS2 by Le Nagard et al 9 indicated a semiconducting behavior. They found unusually low activation energy Eact of around 4meV in the temperature range 60K - 300K and a large conductivity at lower temperatures, thereby indicating non-insulating properties. Another study suggested that CuCrS2 is a non-stoichiometric semiconductor and exhibits changeover from p-type to n-type when prepared under a reduced sulfur-vapor pressure and at higher temperatures10. This study was performed at temperatures above 6000C, so their conclusions are not applicable for the low temperature transport properties. Moreover, Cu(Ag)CrS2 also shows an order-disorder transition of Cu-atoms around 4000C that may affect the electronic transport properties at high temperatures7. Apart from these studies, Cu(Ag)CrS2 has also been characterized as a mixed ion-electron conductor. A large diffusion ionic conductivity of Cu+1- ions on the tetrahedral sites was measured above room temperature11. As far as the electronic conductivity is concerned, one study found very large resistivity ~ 104 Ωcm and the other an immeasurable high resistivity in CuCrS2 at room temperature 12.

## 2. D0005

Matched terms: resistance

The Seebeck coefficients, electric resistance and thermal conductivity have monotonic slope with increasing temperature from 240 to 380 K (Fig.3).

## 3. D0038

Matched terms: resistiv, rho

The chalcogenides are considered to be promising materials for thermoelectric applications [1, 2, 3, 4, 5, 6]. Ag2Se is especially attractive due to it’s high figure of merit (ZT) near room temperature [7, 8] and the abundance of it’s constituent elements on earth’s crust [8]. The β -Ag2Se is also found promising for high field magneto-resistive sensor applications [9]. Ag2Se undergoes a structural transition at Tβ-α = 407 K from a low temperature semiconducting (space group: C2/m) orthorhombic β -phase to a high temperature superionic face centred cubic α -phase (space group: Fm 3 m) [10]. The ZT of β -Ag2Se near 300 K varies from 0.2 to 1.0 depending on the charge carrier concentration (n) [8]. The optimized n = 1.6 × 10^18 cm^-3 for the maximum ZT in β -Ag2Se is small in comparison with other chalcogenides [8]. This creates a challenge for the use of β -Ag2Se based materials in thermoelectric applications as the ionic movement of Ag above Tβ-α results in the segregation of Ag clusters along the grain boundaries [11], thereby changing the dynamics of the system. The temperature dependence of resistivity ρ (T) of β -Ag2Se is semiconducting in the range 320 K <T<Tβ-α [7, 9, 12, 15, 17, 18, 19, 20, 8, 10, 13, 14, 16, 11]. On the other hand, ρ (T) in the range 2-320 K shows a hump at Tmax with metallic behaviour (or positive temperature coefficient of resistivity) below Tmax [7, 9, 12, 15, 17, 18]. The position of Tmax reported by various authors differ significantly viz., 60 K [12, 18], 80 K[9, 18], 100 K[15], and 200 K [7]. Such a behaviour in the temperature dependence of resistivity of degenerate semiconductors can be explained by considering a semiconducting band and a metallic impurity band [21]. However, Santhosh Kumar and Pradeep [22] reported that the ρ (T) of β -Ag2Se thin film during the warming cycle does not match with the cooling cycle in the range 300 K <T<Tβ-α leading to a large hysteresis. Indication of this hysteresis in the ρ (T) of β -Ag2Se thin films was also observed by Damodara Das and Karunakaran [23]. Thermal hysteresis in these results indicate that there is a first-order phase transition [24] from a semiconducting state above Tmax to a metallic/semi metallic state below Tmax. However, no studies are found in the literature on the origin of such a hysteresis. Therefore, understanding the electronic behaviour of Ag2Se is important for utilizing this system for technological applications at room temperature and below.

## 4. D0089

Matched terms: resistiv

In this work we combine studies of GMR and of the giant magneto-thermopower (GMTP) of Co/Cu multilayer devices with investigations of the magnetothermal conductivity of the same stacks [16]. The Seebeck coefficient S = - Vth/ΔT is derived from measurements of the thermopower Vth in lateral thermal gradients ΔT. ΔT is determined by local resistive thermometry in combination with finite element simulations of the temperature distribution. We derive Seebeck coefficients of SP = – 18 μV/K for parallel and SAP = – 14 μV/K for antiparallel spin configuration, a giant magneto-ZT ratio above 65 % and a giant magneto-PF of 110 %.

## 5. D0051

Matched terms: resistiv, rho

In summary, we have synthesized and characterized the thermoelectric properties of pure and chemically-doped FeGa3. The parent compound is a small band-gap semiconductor with a large n-type Seebeck coefficient at room temperature, but the power factor and the corresponding figure of merit are small because of a large electrical resistivity. Even small amounts of chemical doping have a significant effect on the physical properties and electronic structure of the pure compound, which shows a large decrease in resistivity with a corresponding increase in carrier density at room temperature. The Seebeck coefficients of the doped samples remain large, with magnitudes greater than 100 μV/K. The highest power factor (S2/ρ(390 K) = 62 μW / K2 m) and figure of merit (ZT(390 K) = 1.3 × 10-2) at 390K are observed for Fe0.99Co0.01(Ga0.997Ge0.003)3. FeGa3 provides an excellent example of a system where chemical doping can be used to optimize the physical properties in the thermoelectric figure of merit and greatly improve the performance.

## 6. D0034

Matched terms: resistiv, Omega/ohm, resistance

In contrast, the Ni-contacted device only have two distinctive thermoelectric current area (Figure 4(b) and 4(e)), indicating there is almost no band bending within our instrument detecting range at the contact region (Figure 4(h)). This corresponds to the flat-band condition which is represented in Figure 4(b). As we adopting higher work function metal Pd, we noticed that the polarity of photovoltaic current has inverted compared to Cr-contacted device (Figure 4(f) and Figure 4(i)), indicating accumulation-type contacts are formed. This suggests Ni and Pd can form near Ohmic metal-to-semiconductor contacts with essentially no Schottky barrier.It explains why the record low contact resistance can be achieved in 2D Te transistors with Pd contacts22. It is worth mentioning that such accumulation-mode contacts are very rare cases, especially in p-type semiconductors. The tunable contact band bending profile can be ascribed to the Fermi-level depinning effect at van der Waals interfaces. We also noticed that the thermoelectric current is 3 times larger in Pd- and Ni- contacted devices compared to Cr-contacted device, indicating that low resistivity contacts are necessary to collect thermally generated carriers and to harvest the thermoelectric energy more efficiently. By taking advantage of different metal contacts, we can also tune the behavior of 2D Te Schottky transistors (see Figure S2), or implement device structures with versatile functionalities such as Te Schottky diodes with on/off ratio over 103 at room temperature (see Figure S3) and solar cell devices (see Figure S4).

## 7. D0090

Matched terms: resistiv

A small number of materials exhibit exceptionally high electrical conductivity, reaching up to about 500,000 S/m. Such high-conductivity values are essential for optimizing thermoelectric performance, as higher electrical conductivity helps to reduce resistive losses in thermoelectric devices.
The distribution demonstrates that the database includes materials with a wide range of conductivity values, including those suitable for advanced thermoelectric applications.

## 8. D0007

Matched terms: resistiv

We use first-principles electronic structure methods to calculate the electronic thermoelectric properties (i.e. due to electronic transport only) of single-crystalline bulk n -type silicon-germanium alloys vs Ge composition, temperature, doping concentration and strain. We find excellent agreement to available experiments for the resistivity, mobility and Seebeck coefficient. These results are combined with the experimental lattice thermal conductivity to calculate the thermoelectric figure of merit ZT, finding very good agreement with experiment. We predict that 3% tensile hydrostatic strain enhances the n -type ZT by 50% at carrier concentrations of n=10^20 cm^-3 and temperature of T=1200K. These enhancements occur at different alloy compositions due to different effects: at 50% Ge composition the enhancements are achieved by a strain induced decrease in the Lorenz number, while the power factor remains unchanged. These characteristics are important for highly doped and high temperature materials, in which up to 50% of the heat is carried by electrons. At 70% Ge the increase in ZT is due to a large increase in electrical conductivity produced by populating the high mobility conduction band valley, lowered in energy by strain.

## 9. D0002

Matched terms: resistiv

Figure 4 (b) shows the variation of electrical conductivity (σ) for all the composite sample from 320-800 K measured using standard DC four-probe technique. It has been observed that at 320 K the conductivity is maximum for x=0.00 and decreases slightly with the increase in the value of x in the composite. This suggests that addition of LSMO in LCO enhances the interaction between different electronic states of Co3+ and Mn3+ leading to the localization of eg1 electrons and hence resistivity increases. It is also believed that electronic states in manganites are more localized compared to that of cobaltate [31]. It has been observed that all the sample shows an increase in conductivity with an increase in temperature. The maximum value of conductivity was found to be ≈59000 S/m for x=0.00 at 800 K and the value is identical for x=0.05 sample at the same temperature. However, with the increase in the value of x in the composite, the value of conductivity decreases compared to the parent system. The increase in electrical conductivity with an increase in temperature shows the semiconducting nature of the composite samples.

## 10. D0099

Matched terms: Omega/ohm

Fig. 3 (a) show our experimental data obtained using the four-terminal probe method [26] in the samples prepared using the spark plasma sintering (SPS)
technique. Two sets of measurements before (violet circles) and after (red and green squares) annealing have been performed. As expected,
annealing improves the electrical conductivity [27, 11] which reaches its maximum value of σ=1036 (Ω cm)^-1 at
T = 350 K and then starts monotonically decreasing at higher temperatures. We notice that our results are much lower than the electrical conductivity σ=1700 Ω^-1 cm^-1
measured in the intrinsic samples at T = 300 K [12, 11]. These intrinsic samples were prepared by multiple annealing of the originally p -type samples in the presence
of Hg gas [12, 11]. However, in this work we do not follow this procedure due to the extreme toxicity of mercury.

## 11. D0054

Matched terms: resistiv, rho

In [46], it has been shown that a kink-like transition is observed around the Neel temperature in both the thermopwer and electrical resisitivity of MnBi2Te4. Upon approaching TN, spin fluctuations are expected to be stronger, leading to stronger scattering and thus a shorter mean-free-path of electrons and an increase in resistivity. As the long-range magnetic order develops below TN, in which spins within the x-y plane are ferromagnetically aligned, spin fluctuations and the electron-spin scattering are suppressed, resulting in kink in ρ at TN followed by a continuous decease upon decreasing the temperature. For thermopower, its negative sign over the whole
measured temperature range suggests electrons as the dominant charge carriers, which is consistent with the Hall effect transport studies. As the temperature decreases, the entropy per electron decreases, leading to a decrease in thermopower, on the other hand, as will be discussed later, below TN the magnon-electron drag effect due to the coherent momentum conserving magnon-electron scattering gives rise to an increase in thermopower. As a result, the net thermopower develops a broad bump around 14 K.
The maximum electron contribution below 25 K is 0.05 W/mK, much smaller than the increase of thermal conductivity observed below TN. Therefore, the main heat carriers in MnBi2Te4 are phonons and/or magnons. Magnons can contribute to the thermal conduction via two ways. One is that magnons
serve as heat carriers, which would lead to an enhanced thermal conductivity below TN, the other is that magnons scatter phonons, giving rise to a reduction of the phonon contribution to thermal conductivity. Thus, the increase of thermal conductivity below TN indicates the dominance of magnons as heat carriers.

## 12. D0065

Matched terms: rho, Omega/ohm

×10-8 W·Ω·K-2 with α in μV·K-1. [45] 2.4.1. Phonon thermal conductivity and Bruggeman’s model: Temperature-dependent κph for (1-z)Ge0.87Mn0.05Sb0.08Te/(z)WC composite is shown in Fig.7(b). It is worth noting that κph of the composite decreases with the increase in temperature, and interestingly, it also decreases with the increase in WC volume fraction. The changes in electronic (κe) and phonon thermal conductivity (κph) with an increase in WC volume fraction at 300 K are shown in the inset of Fig.7(b). It is noted that κph of WC is relatively higher (~135 W·m-1·K-1 at 300 K) as compared to Ge0.87Mn0.05Sb0.08Te. However, κph of the composite decreases with the addition of the WC volume fraction. This decrease in κph for composite is interesting and is analyzed using Bruggeman’s asymmetrical model that considers Rint between the phases in the composite. The Rint for the composite is estimated using the AIM and the Debye model.[46,47] The AIM model shows that the phonon propagating from one material to another can be reflected if there is a mismatch in the acoustic impedance (Z=v×ρ) between the two materials, where v is the sound velocity, and ρ is the sample density.[30] The sound velocity (v) and sample density (ρ) measured for both Ge0.87Mn0.05Sb0.08Te and WC and their calculated acoustic impedance are presented in Table I. The probability of phonon transmission (η = pq) at the interface between Ge0.87Mn0.05Sb0.08Te (matrix) and WC (dispersed phase) is 0.0436, where p =

## 13. D0040

Matched terms: resistiv, rho

Figure 2 shows the in-plane resistivity, ρa, out-of-plane resistivity,
 ρc, and anisotropy ratio, ρa/ρc.
Both ρa and ρc exhibited metallic behaviors, and they almost depend on T^2 
(ρa T^2.18, ρc T^1.78).
Figure 3 shows the in-plane carrier density, n=1/RHe and
the inverse Hall mobility 1/μH=ρ/RH as a function of T.
The carrier density at room temperature is 2.8× 10^20 cm^-3 and almost independent of T.
If the Ti^4+ state is assumed, this carrier density
gives the amount of excess titanium to be 0.0001 atoms/f.u.,
which indicates that the chemical composition of this crystal is very close to the stoichiometry. [16]
It is noted here that this carrier density in TiS2 is still
one order of magnitude larger than that in thermoelectric Bi2Te3 with optimum carrier density.

## 14. D0082

Matched terms: resistiv

GB (3x10 18) experimentally reported trends in thermal resistivity vs. grain density [17, 43]. The doping density of the grain boundaries was set at 18 -3 3 10 cm GB A N = × to produce results consistent with experiments. The resulting band bending is about one-half of the band gap. As shown in Fig. 2(b), the result was that the Seebeck coefficient of the grain boundaries was substantially higher than that of the grains. The generated polycrystalline geometry was used as an input to the Sentaurus Device simulator. It was critical to resolve the band bending within and near the grain boundaries. For polycrystalline materials, a fine mesh on both sides of the grain boundary was needed. The added burden of a dense mesh is the main reason why we used 2D simulations instead of 3D. A full 3D simulation of a geometry that is large enough to be statistically meaningful would have taken days. As discussed in Sec. VI, simulations of 1D nanocomposites show results that are very similar to those obtained by 2D simulations; it is likely, therefore, that the effects found in the 2D studies would not change in 3D. (See the supplementary information for a description of how the 1D simulations were done.) The Sentaurus simulations used tables of transport parameters vs. carrier density for all thermoelectric parameters; these tables were generated using LanTraP with the aforementioned DFT calculations. Phenomena such as the Thomson effect and mobility variations with doping density were, therefore, automatically included. For each random sample, we computed the conductivity by applying a small voltage (0.1 mV), computing the resulting current, and converting the result to a conductivity for the sample. To compute the Seebeck coefficient and thermal conductivity, we applied a small temperature difference (1 K), and simulated the resulting open circuit voltage, which yields the Seebeck coefficient and heat flux, from which, we determine the thermal conductivity. From the three parameters, we could compute a material figure of merit, zT, for the sample. We also determined the zT by simulating a Harman measurement [34] for each sample. Finally, we extracted a zT by simulating the max T ∆ of an ideal 1-leg TE cooler. The results of 100 such simulations for each average grain size were averaged and plotted. III. Results The simulated Seebeck coefficient for polycrystalline Bi2Te3 as a function of average grain size is shown in Fig. 3(a). Because the simulation domain (1 mm by 1 mm) is large enough to contain thousands of grains, significant grain size averaging occurs for each randomly generated sample. Still, for each average grain size, 100 randomly generated samples were simulated and averaged. The error bars shown in Fig. 3(a) show that the sample-to-sample variation is small. As intuitively expected, with decreasing average grain size, the Seebeck coefficient increases because the grain boundary regions have higher Seebeck coefficients, and as the average grain size decreases, there are more grain boundaries. Still, the size of the grain boundaries is small, so the grain boundary regions occupy a small fraction of the polycrystalline sample. If we repeat the simulation but assume no reduction in lattice thermal conductivity, then as Fig. 3(a) shows, there is a much smaller dependence of the Seebeck coefficient on grain size.

## 15. D0052

Matched terms: resistiv

The influence of strain on the thermoelectric properties is notable. This is manifested in the significant increase in the previously defined power-factor temperature product, PFxT, as synthesis temperature increased, by as much as 50% across the five samples shown in Figure 4. Among the samples produced by SPS, this resulted in a 20% increase in zT, from 1 to 1.2. The large increase in power factor, which is partly responsible for the increase in zT, can be attributed to the decrease in charge-carrier density and increase in carrier mobility. This finding is consistent with the increase in size of the bandgap inferred from resistivity measurement [11]. The reduced lattice strain has apparently resulted in the disappearance of most of the in-gap defect states associated with antisite disorder [30] that scatter charge carriers.

## 16. D0014

Matched terms: resistiv, rho

The calculated power factor (S2/ρ) shows a large increment (Figure 4c) in the range of temperature from 200 K to 400 K over that of pure FeGa3. This is primarily because of the significant decrease in the electrical resistivity of the doped samples from that of the pure compound, while maintaining a fairly high thermoelectric power. The effect of the improvement in the power factor can be identified by observing the significant increase in the thermoelectric figure of merit (Figure 4d) of the chemically-doped compound over the whole range of temperature. The largest figure of merit (ZT(390 K)Fe0.99Co0.01(Ga0.997Ge0.003)3 = 1.3 × 10-2) increases by a factor of 5.6 over that of pure FeGa3.

## 17. D0030

Matched terms: resistiv

FeAs2 is an insulator with a gap of 0.2-0.22 eV [23, 14], as obtained from the activation behavior in the resistivity at temperatures of 200K and higher.
Below 200K, the influence of impurities is pivotal[23, 14]: the resistivity has a metallic slope before resuming, below 30K and down to 10K, an activation
law with an energy of 0.01eV. Further, below 10K, the resistivity exhibits activation with 6K (0.5meV).[14]
The Hall coefficient is negative for all temperatures [23]. Congruently, the Seebeck coefficient is negative as well: From its room temperature value
 -200μV/K [23], it grows in magnitude upon cooling, to reach -7 mV/K at 12K,[14] before it vanishes towards zero temperature.[14]

## 18. D0062

Matched terms: resistiv, resistance

Numerous experiments [21, 22, 23, 24], particularly those investigating giant magnetoresistance (GMR) phenomena [22], have demonstrated that spins orientation in magnetic materials significantly influences their electrical resistivity. In particualr, they reveal that the resistivity increases in the paramagnetic phase where the spins are randomly oriented. This behavior is attributed to the formation of magnetic clusters, whose size and number are temperature-dependent. In the following sections, we demonstrate that magnetic clustering on the surface of magnetic TIs, significantly influences the transport properties of the system. We define magnetic clusters within the Ising and Heisenberg models separately, and determine their size and number’s temperature dependence using Monte Carlo (MC) simulations.

## 19. D0046

Matched terms: Omega/ohm

Table 3: Highest ZT values for both n-type and p-type systems and corresponding
optimal TE parameters for HfRhBi, ZrIrBi and ZrRhBi at 1300 K and
900 K. T, nc, S, S ^2σ, σ, κL and κ are in the units of Kelvin, 10^20 cm^-3, μVK^-1, mWm^-1K^-2, 10^4 Ω^-1 m^-1, mWm^-1K^-1 and mWm^-1K^-1 respectively.

## 20. D0096

Matched terms: Omega/ohm

The Wiedemann-Franz law was applied to obtain κe via relation κe = LσT, where L is the Lorentz number, electrical conductivity (σ), and temperature (T). And, κL value was calculated by subtracting κe value from κ value.29 The exact value of κe is achieved via calculating correct estimation of L with temperature. The temperature dependent L for all the samples is displayed in Fig. 7(a). Fig. 7(b) presents L vs α for the entire composite samples and also with the estimated L value through SPB-APS model30 or can be described as a single parabolic band with acoustic phonon scattering model. This fitting also shows the degenerated limit of the Lorentz number L= 2.4 x 10-8 W ohm K-2. 30

## 21. D0060

Matched terms: resistiv

Abstract Half Heusler (HH) alloys with 18 valence electron count have attracted significant interest in the area of research related to thermoelectrics. Understanding the novel transport properties exhibited by these systems with semiconducting ground state is an important focus area in this field. Large thermal conductivity shown by most of the HH alloy possesses a major hurdle in improving the figure of merit (ZT). Additionally, understanding the mechanism of thermal conduction in heavy constituents HH alloys is an interesting aspect. Here, we have investigated the high temperature thermoelectric properties of ZrIrSb through experimental studies, phonon dispersion and electronic band structure calculations. ZrIrSb is found to exhibit substantially lower magnitude of resistivity and Seebeck coefficient near room temperature, owing to existence of anti-site disorder between Ir/Sb and vacant sites. Interestingly, in ZrIrSb, lattice thermal conductivity is governed by coupling between the acoustic and low frequency optical phonon modes, which originates due to heavier Ir/Sb atoms. This coupling leads to an enhancement in the Umklapp processes due to the optical phonon excitations near zone boundary, resulting in a lower magnitude of κL. Our studies point to the fact that the simultaneous existence of two heavy mass elements within a simple unit cell can substantially decrease the lattice degrees of freedom.

## 22. D0066

Matched terms: resistiv, rho, Omega/ohm

If one compares the measured ρ values inside the two phase regions with those for polycrystalline Cu2Se, it is seen that the CuAgSe has an electrical resistivity comparable with that of the Cu2Se. Typically, Cu2Se has the ρ ~10 μΩ⋅m and 30 μΩ⋅m at T ~323 K and 600 K, respectively, while CuAgSe has ρ ~ 8 μΩ⋅m and ~58 μΩ⋅m at the two temperatures. Here the low ρ values of the α-CuAgSe are ascribed to the fact that the α-CuAgSe phase is a semimetal and has high carrier mobility, to be confirmed below. The slightly higher electrical resistivity of the β-CuAgSe phase is due to the random mixing of Cu and Ag atoms, which brings additional scattering to electron transport with respect to β-Cu2Se phase, which is why the electrical resistivity of β-CuAgSe is higher than that of β-Cu2Se.

## 23. D0076

Matched terms: resistiv, rho, Omega/ohm

The resistivity-anisotropy ratios are large: 750 at 300 K and 1500 at 5 K.
These ratios suggest that doped electron carriers are confined within the TiS6 layers,
thus, the electronic structure of TiS2 is quasi two-dimensional.
In-plane Hall mobility strongly depends on T (1/μH T^2.14)
and decreases with increasing T from 150 cm^2/Vs at 5 K to 15 cm^2/Vs at 300 K.
The significant increase in ρ with increasing T 
arises from the increase in scattering rate (1/μH).
The metal-like temperature dependence of ρc in the order of about 1 Ω cm is quite unusual.
Although we cannot explain the dependence of ρc on T satisfactorily,
the random network of marginally metallic paths along the c -axis between the metallic layers can give rise to it.

## 24. D0023

Matched terms: rho

The thermoelectric degrees of freedom can be directly estimated from the material properties using formula equation (2) for Z_gen^(0), τ^(0)lin and β^(0)lin.
To derive the formula, we assume the temperature distribution inside the leg to be T^(0), which is the temperature distribution for the J=0 case (i.e., -κdTdx=const.); the superscript (0) means we use the J=0 case. Furthermore, we assume the material properties α and ρ×κ are linear with respect to T; the subscripts in τ^(0)lin and β^(0)lin emphasize this linearity.
We then have the formula equation (2); see §10 and §11 in SI for its derivation and accuracy. The general device power factor can be similarly estimated as
 P F gen^(0)=Z_gen^(0) κ dT.
This one-shot approximation clarifies the relationship between the material properties and the thermoelectric efficiency; for example, because τ≈-13αh-αcαh+αc, the τ (and the efficiency) can be enhanced if the α(T) declines more rapidly on T.
The one-shot approximation is accurate even for segmented devices. The performance of two-stage segmented device composed of SnSe and BiSbTe at Δ T=660K-320K is well described by ηmax(Z_gen^(0),τ^(0),β^(0)|γ) over the whole γ range for power generation; see §10 and Figure S5 in SI.
Moreover, in high-performance materials, higher Z_gen^(0) usually implies higher thermoelectric efficiency even for segmented materials. Hence the top-ranked devices in order of their efficiency can be screened out quickly by using Z_gen^(0) only.
As an example, the efficiencies of 5-stage segmented devices comprised of 18 candidate materials are computed. Of nearly two million combinations of the segmented legs (18^5=1,889,568), a top 1% high- Z_gen^(0) device is also a top 1% high-efficiency device with 82% probability; see §12 in SI.
