import * as DigitalBaconUI from 'DigitalBacon-UI';
import * as THREE from 'three';


  const labelStyle = new DigitalBaconUI.Style({
    color: '#ffffff',
    fontSize: 0.07,
    marginLeft: 0.02,
  });
  const spanStyle = new DigitalBaconUI.Style({
    height: 0.1,
    marginLeft: 0.02,
  });


export class TelescopeGUI {

    static async init(container, renderer, scene, camera, userRig) {
        await DigitalBaconUI.init(container, renderer, scene, camera);
        DigitalBaconUI.InputHandler.enableXRControllerManagement(userRig);
    }

    static createVisibilityGUI(scene, userRig, settings, starfield, sim, telescope) {
        const gui = new TelescopeGUI(scene, userRig, settings, starfield, sim, telescope);
        gui._makeVisibilityGUI();
        return gui;
    }
    
    update(frame)   {
        DigitalBaconUI.update(frame);
    }

    show() {
        this.isShown = true;

        const controller = this.sim.controllers.Left;
        const camera = this.sim.camera; 

        // Local offset in controller space
        const offset = new THREE.Vector3(0, 0, -0.6); // 60cm in front of controller

        // Add the GUI to userRig and place it at the calculated local position
        this.userRig.add(this.body);
        if(controller) {
          this.body.position.copy(offset.applyMatrix4(controller.matrix));
        }

        // Make the GUI face the camera (also in userRig space)
        const cameraWorldPos = new THREE.Vector3().setFromMatrixPosition(camera.matrixWorld);
        this.body.lookAt(cameraWorldPos);

        // Tilt back slightly
        this.body.rotateX(THREE.MathUtils.degToRad(-15));

        // Scale the GUI
        const scale = 0.5;
        this.body.scale.set(scale, scale, scale);
    }

    hide() {
        this.isShown = false;
        this.userRig.remove(this.body);
        this.sim.saveSettings();
    }

    toggle() {
        if(this.isShown) this.hide(); else this.show();
    }



    constructor(scene, userRig, settings, starfield, sim, telescope) {

        this.isShown = false;
        this.scene = scene;
        this.userRig = userRig;
        this.settings = settings;
        this.starfield = starfield;
        this.sim = sim;
        this.telescope = telescope;
    }

    _makeVisibilityGUI(){
          const starfield = this.starfield;

          const body = new DigitalBaconUI.Body({
            borderRadius: 0.05,
            borderWidth: 0.001,
            backgroundVisible: false,
            justifyContent: 'spaceBetween',
            width: 1.5,
            height: 1.5
          });
          const row1 = new DigitalBaconUI.Span({
            borderTopLeftRadius: 0.05,
            borderTopRightRadius: 0.05,
            height: 0.1,
            width: '100%',
            justifyContent: 'center',
            backgroundVisible: true,
            materialColor: '#aaaaaa',
          });
          body.add(row1);
          const text1 = new DigitalBaconUI.Text('PipiVR', {
            fontSize: 0.08,
            color: '#ffffff',
          });
          row1.add(text1);

          const row2 = new DigitalBaconUI.Span({
            height: 1.3,
            width: '100%',
            justifyContent: 'center',
            backgroundVisible: true,
            materialColor: '#aaaaaa',
            borderRadius: 0.05,
          });
          body.add(row2);


          const section1 = new DigitalBaconUI.Div({
            alignItems: 'start',
            padding: 0.0,
            height: '100%',
            width: '30%',
          });
          row2.add(section1);

          const section2 = new DigitalBaconUI.Div({
            alignItems: 'center',
            padding: 0.0,
            height: '100%',
            width: '35%',
          });
          row2.add(section2);

          const section3 = new DigitalBaconUI.Div({
            alignItems: 'center',
            padding: 0.0,
            height: '100%',
            width: '35%',
          });
          row2.add(section3);

          section1.add(new DigitalBaconUI.Text('  object', {
            fontSize: 0.08,
            color: '#ffffff',
          }));

          section2.add(new DigitalBaconUI.Text('visibility', {
            fontSize: 0.08,
            color: '#ffffff',
          }));
          section3.add(new DigitalBaconUI.Text('mag. limit', {
            fontSize: 0.08,
            color: '#ffffff',
          }));


          this.createCheck(section1, 
              'Stars', this.settings.showStars, 
              (value) => {
                this.settings.showStars = value; 
                starfield.enableCatalogs('star',value);
              }
          );
          this.createCheck(section1, 
              'Galaxies', this.settings.showGalaxies, 
              (value) => {
                this.settings.showGalaxies = value; 
                starfield.enableCatalogs('galaxy',value);
              }
          );

          this.createCheck(section1, 
              'Nebulae', this.settings.showNebulae, 
              (value) => {
                this.settings.showNebulae = value; 
                starfield.enableCatalogs('nebula',value);
              }
          );
          this.createCheck(section1, 
              'Clusters', this.settings.showClusters,
              (value) => {
                this.settings.showClusters = value;
                starfield.enableCatalogs('cluster',value);
              }
          );
          this.createCheck(section1, 
              'Images', this.settings.showImages,
              (value) => {
                this.settings.showImages = value;
                starfield.enableCatalogs('image',value);
              }
          );

          this.createRange(section2,
              '', this.settings.starBrightness,
              (value) => {
                this.settings.starBrightness = value;
                starfield.refilterCatalog('star');
              }
          );
          this.createRange(section3,
              '', this.settings.minStarMagnitude/6.5,
              (value) => {
                this.settings.minStarMagnitude = value*6.5;
                starfield.refilterCatalog('star');
              }
          );
          

          this.createRange(section2,
              '', this.settings.galaxyBrightness,
              (value) => {
                this.settings.galaxyBrightness = value;
                starfield.refilterCatalog('galaxy');
              }
          );
          this.createRange(section3,
              '', (this.settings.minGalaxyMagnitude - 10)/12,
              (value) => {
                this.settings.minGalaxyMagnitude = 10 + value*12;
                starfield.refilterCatalog('galaxy');
              }
          );

          this.createRange(section2,
              '', this.settings.nebulaBrightness,
              (value) => {
                this.settings.nebulaBrightness = value;
                starfield.refilterCatalog('nebula');
              }
          );
          this.createRange(section3,
              '', (this.settings.minNebulaMagnitude - 10)/12,
              (value) => {
                this.settings.minNebulaMagnitude = 10 + value*12;
                starfield.refilterCatalog('nebula');
              }
          );

          this.createRange(section2,
              '', this.settings.clusterBrightness,
              (value) => {
                this.settings.clusterBrightness = value;
                starfield.refilterCatalog('cluster');
              }
          );
          this.createRange(section3,
              '', (this.settings.minClusterMagnitude - 10)/12,
              (value) => {
                this.settings.minClusterMagnitude = 10 + value*12;
                starfield.refilterCatalog('cluster');
              }
          );

          this.createRange(section2,
              '', this.settings.imageBrightness,
              (value) => {
                this.settings.imageBrightness = value;
                starfield.refilterCatalog('image');
              }
          );
          section3.add(new DigitalBaconUI.Span(spanStyle));


          this.createCheck(section1, 
              'Ground', this.settings.showGround,
              (value) => {
                this.settings.showGround = value;
                this.sim.ground.visible = value;
              }
          );
          this.createRange(section2,
              '', this.settings.groundBrightness,
              (value) => {
                this.settings.groundBrightness = value;
              }
          );
          this.createRange(section3,
              '', this.sim.ground.material.opacity,
              (value) => {
                this.sim.ground.material.opacity = value;
              }
          );

          

          this.createCheck(section1, 
              'Gravity', this.settings.gravity, 
              (value) => {this.settings.gravity = value;}
          );

          this.createCheck(section1, 
              'Telescope', this.settings.showTelescope, 
              (value) => {this.settings.showTelescope = value; this.telescope.setVisible(value);}
          );

          this.createCheck(section1, 
              'Music', this.settings.playMusic, 
              (value) => {
                this.settings.playMusic = value;
                if(!this.sim.music) return;
                if(value) {
                  this.sim.music.play();
                } else {
                  this.sim.music.stop();
                }
              }
          );

          this.createButton(section1, 'Save catalog',  
              () => {
                this.sim.saveCatalog();
              }
          );

          

          this.body = body;

/*          const toggle2 = new DigitalBaconUI.Toggle({ borderRadius: 0.04 });
          const toggle2Span = new DigitalBaconUI.Span();
          const toggle2Label = new DigitalBaconUI.Text('Toggle', labelStyle);

          const checkbox1 = new DigitalBaconUI.Checkbox();
          const checkbox1Span = new DigitalBaconUI.Span();
          const checkbox1Label = new DigitalBaconUI.Text('Checkbox', labelStyle);
          const checkbox2 = new DigitalBaconUI.Checkbox({ borderRadius: 0.04 });
          const checkbox2Span = new DigitalBaconUI.Span();
          const checkbox2Label = new DigitalBaconUI.Text('Checkbox', labelStyle);
          const radio1 = new DigitalBaconUI.Radio('radioName');
          const radio1Span = new DigitalBaconUI.Span();
          const radio1Label = new DigitalBaconUI.Text('Radio', labelStyle);
          const radio2 = new DigitalBaconUI.Radio('radioName');
          const radio2Span = new DigitalBaconUI.Span();
          const radio2Label = new DigitalBaconUI.Text('Radio', labelStyle);
          const radio3 = new DigitalBaconUI.Radio('radioName');
          const radio3Span = new DigitalBaconUI.Span();
          const radio3Label = new DigitalBaconUI.Text('Radio', labelStyle);
          section1.add(toggleGSpan);
          section1.add(toggle2Span);
          section1.add(checkbox1Span);
          section1.add(checkbox2Span);
          section2.add(radio1Span);
          section2.add(radio2Span);
          section2.add(radio3Span);
          toggle2Span.add(toggle2);
          toggle2Span.add(toggle2Label);
          checkbox1Span.add(checkbox1);
          checkbox1Span.add(checkbox1Label);
          checkbox2Span.add(checkbox2);
          checkbox2Span.add(checkbox2Label);
          radio1Span.add(radio1);
          radio1Span.add(radio1Label);
          radio2Span.add(radio2);
          radio2Span.add(radio2Label);
          radio3Span.add(radio3);
          radio3Span.add(radio3Label);
          row2.material.color.setHSL(0, 0, 0.5);
          */
          
     

    }

    createCheck(parent, label, value, onChangeCallback) {
      const element = new DigitalBaconUI.Checkbox();
      const span = new DigitalBaconUI.Span(spanStyle);
      const labelText = new DigitalBaconUI.Text(label, labelStyle);
      element.checked = value;
      span.add(element);
      span.add(labelText);
      element.onChange = (value) => onChangeCallback(value);
      parent.add(span);
      return span;
    }

    createRange(parent, label, value, onChangeCallback) {
      const range = new DigitalBaconUI.Range({ width: 0.45 });
      const span = new DigitalBaconUI.Span(spanStyle);
      const labelText = new DigitalBaconUI.Text(label, labelStyle);
      range.value = value;
      span.add(range);
      span.add(labelText);
      range.onChange = (value) => onChangeCallback(value);
      parent.add(span);
      return span;
    }

    createButton(parent, label, onClickCallback) {
      const button = new DigitalBaconUI.Div({ width: 0.45, materialColor: 0x1db954, backgroundVisible: true,});
      const span = new DigitalBaconUI.Span(spanStyle);
      const labelText = new DigitalBaconUI.Text(label, labelStyle);
      span.add(button);
      button.add(labelText);
      button.onClick = () => onClickCallback();
      parent.add(span);
      return span;
    }
}    